"""Guarded batch commands embedded in the portable scanner executable.

The commands keep file names as subprocess arguments, never shell text. Cleanup
is serial, backup-preserving, and followed by a fresh signature scan.
"""

# Import future modules
from __future__ import annotations

# Import built-in modules
import argparse
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile


NO_INFECTION_MARKER = "No infected files found."
MANIFEST_MARKER = "Export infected files to:"
REPORT_SCHEMA_VERSION = 1
MIN_FREE_BYTES = 64 * 1024 * 1024


class BatchScanError(RuntimeError):
    """Raised when a batch operation cannot proceed safely."""


@dataclass(frozen=True)
class ProcessResult:
    """Captured scanner subprocess result."""

    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ApprovedScan:
    """Validated cleanup evidence and its immutable content digest."""

    path: Path
    sha256: str
    findings: dict[str, dict[str, str]]


Runner = Callable[..., ProcessResult]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the bounded scan and clean contracts."""
    parser = argparse.ArgumentParser(description="Batch Maya scene antivirus runner")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--scanner",
        help="Override the scanner executable (default: this portable CLI)",
    )
    common.add_argument("--path", action="append", required=True, dest="paths", help="Target directory; repeatable")
    common.add_argument("--report", help="Optional JSON report path")

    subparsers = parser.add_subparsers(dest="mode", required=True)
    subparsers.add_parser("scan", parents=[common], help="Read-only signature scan")

    clean = subparsers.add_parser("clean", parents=[common], help="Backup, clean, and verify")
    clean.add_argument("--maya-version", required=True, help="Installed Maya year, for example 2024")
    clean.add_argument(
        "--approved-scan-report",
        required=True,
        help="The completed scan report whose exact findings the user approved",
    )
    clean.add_argument(
        "--approved-scan-report-sha256",
        required=True,
        help="SHA-256 printed by scan for the exact report bytes the user approved",
    )
    clean.add_argument(
        "--confirm-clean",
        action="store_true",
        help="Required acknowledgement that cleanup mutates approved scenes; references need separate approval",
    )
    return parser.parse_args(argv)


def resolve_scanner(value: str | None) -> str:
    """Resolve a scanner path without invoking a shell."""
    if value is None:
        executable = Path(sys.executable)
        if (
            getattr(sys, "frozen", False)
            or executable.stem.lower() in {"maya_umbrella", "maya-umbrella-scanner"}
        ) and executable.is_file():
            return str(executable.resolve())
        value = "maya_umbrella"
    candidate = Path(value).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    resolved = shutil.which(value)
    if resolved:
        return str(Path(resolved).resolve())
    raise BatchScanError(f"Scanner executable was not found: {value}")


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((os.path.normcase(str(path)), os.path.normcase(str(root)))) == os.path.normcase(
            str(root)
        )
    except ValueError:
        return False


def _lexical_path(value: str | Path) -> Path:
    """Normalize an absolute path without following a newly introduced redirect."""
    return Path(os.path.abspath(os.path.expanduser(str(value))))


def _ensure_no_reparse_points(path: Path) -> Path:
    """Reject symlinks and Windows junctions in every existing path component."""
    lexical = _lexical_path(path)
    for component in reversed((lexical, *lexical.parents)):
        if str(component) == component.anchor:
            continue
        if not os.path.lexists(component):
            raise BatchScanError(f"Approved path component no longer exists: {component}")
        if _is_reparse_point(component):
            raise BatchScanError(f"Approved cleanup paths cannot contain symlinks or junctions: {component}")
    return lexical


def normalize_targets(values: Iterable[str], cleaning: bool) -> list[Path]:
    """Resolve, validate, and de-duplicate target directories."""
    targets: list[Path] = []
    home = Path.home().resolve()
    for value in values:
        try:
            lexical_target = _lexical_path(value)
            if cleaning:
                _ensure_no_reparse_points(lexical_target)
            target = lexical_target.resolve(strict=True)
        except OSError as exc:
            raise BatchScanError(f"Target does not exist or cannot be resolved: {value}: {exc}") from exc
        if not target.is_dir():
            raise BatchScanError(f"Target must be a directory: {target}")
        if cleaning and (target == Path(target.anchor) or target == home):
            raise BatchScanError(f"Cleanup target is too broad; choose a subdirectory: {target}")

        if any(_is_within(target, existing) for existing in targets):
            continue
        targets = [existing for existing in targets if not _is_within(existing, target)]
        targets.append(target)
    return targets


def validate_backup_folder_name(value: str) -> str:
    """Reserve one fixed quarantine name so arbitrary project trees cannot be hidden."""
    if value != "_virus":
        raise BatchScanError("Backup folder name must remain the reserved value _virus.")
    return value


def invoke_scanner(
    scanner: str,
    target: Path,
    maya_version: str | None,
    env: dict[str, str],
    approved_scan_report: str | None = None,
    approved_report_sha256: str | None = None,
) -> ProcessResult:
    """Run one scanner process using an argument vector."""
    command = [scanner, "--path", str(target)]
    if maya_version:
        command.extend(("--maya-version", maya_version))
    if approved_scan_report:
        command.extend(("--approved-scan-report", approved_scan_report))
    if approved_report_sha256:
        command.extend(("--approved-scan-report-sha256", approved_report_sha256))
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        errors="replace",
        env=env,
        check=False,
    )
    return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


def _read_manifest(path: Path, target: Path) -> list[Path]:
    if not path.is_file():
        raise BatchScanError(f"Scanner reported a missing infection manifest: {path}")
    entries: list[Path] = []
    for raw_line in path.read_bytes().splitlines():
        text = raw_line.decode("utf-8-sig", errors="replace").strip()
        if not text:
            continue
        entry = Path(text).expanduser().resolve(strict=False)
        if not _is_within(entry, target):
            raise BatchScanError(f"Infection manifest escaped the requested target: {entry}")
        if not entry.is_file():
            raise BatchScanError(f"Infection manifest contains a missing file: {entry}")
        if entry in entries:
            raise BatchScanError(f"Infection manifest contains a duplicate file: {entry}")
        entries.append(entry)
    if not entries:
        raise BatchScanError(f"Scanner reported an empty infection manifest: {path}")
    return entries


def interpret_scan(result: ProcessResult, target: Path) -> list[Path]:
    """Convert the scanner's stable messages into a fail-closed observation."""
    combined = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0:
        raise BatchScanError(f"Signature scan failed with exit code {result.returncode}: {combined.strip()}")
    claims_clean = NO_INFECTION_MARKER in result.stdout
    # v0.1.8 reported ripgrep's normal no-match status as an exception before
    # printing its clean marker. Accept only the explicit status-1 combination;
    # every other legacy subprocess exception remains indeterminate.
    legacy_no_match = bool(re.search(r"returned non-zero exit status 1\.", combined)) and claims_clean
    if ("returned non-zero exit status" in combined and not legacy_no_match) or "Signature scan failed" in combined:
        raise BatchScanError(f"Signature scan reported an internal failure: {combined.strip()}")

    manifest_values = [
        line.split(MANIFEST_MARKER, 1)[1].strip().strip('"')
        for line in result.stdout.splitlines()
        if MANIFEST_MARKER in line
    ]
    if claims_clean and manifest_values:
        raise BatchScanError("Scanner output was contradictory (clean and infected).")
    if claims_clean:
        return []
    if len(manifest_values) != 1:
        raise BatchScanError(f"Scanner output was ambiguous: {combined.strip()}")
    return _read_manifest(Path(manifest_values[0]), target)


def sha256_file(path: Path) -> str:
    """Hash a file without loading a Maya scene into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_findings(files: Sequence[Path]) -> dict[str, str]:
    """Bind an approval to both infected paths and their current bytes."""
    return {str(path): sha256_file(path) for path in files}


def _is_reparse_point(path: Path) -> bool:
    """Return whether a filesystem entry can redirect access elsewhere."""
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return path.is_symlink() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _prepare_backup_directory(source: Path, backup_folder_name: str, *, create: bool) -> Path:
    """Validate that the reserved backup directory is a real local child."""
    _ensure_no_reparse_points(source)
    source_parent = source.parent.resolve(strict=True)
    backup_directory = source_parent / backup_folder_name
    if not os.path.lexists(backup_directory):
        if not create:
            return backup_directory
        try:
            backup_directory.mkdir()
        except FileExistsError:
            # Another process created it after the no-entry check; validate it below.
            pass
    if _is_reparse_point(backup_directory) or not backup_directory.is_dir():
        raise BatchScanError(f"Backup directory must be a regular local directory: {backup_directory}")
    try:
        resolved_directory = backup_directory.resolve(strict=True)
    except OSError as exc:
        raise BatchScanError(f"Backup directory cannot be resolved safely: {backup_directory}: {exc}") from exc
    if resolved_directory.parent != source_parent or resolved_directory.name != backup_folder_name:
        raise BatchScanError(f"Backup directory escaped the scene directory: {backup_directory}")
    return backup_directory


def _copy_backup_exclusive(source: Path, backup: Path) -> None:
    """Copy one backup without following or overwriting an existing entry."""
    descriptor: int | None = None
    created = False
    try:
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        destination = os.fdopen(descriptor, "wb")
        descriptor = None
        with destination, source.open("rb") as source_stream:
            shutil.copyfileobj(source_stream, destination, length=1024 * 1024)
        shutil.copystat(source, backup, follow_symlinks=False)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            try:
                backup.unlink()
            except OSError:
                pass
        raise BatchScanError(f"Unable to stage backup without overwriting another file: {backup}: {exc}") from exc


def load_approved_scan(
    path_value: str,
    expected_sha256: str,
    scanner: str,
    targets: Sequence[Path],
) -> ApprovedScan:
    """Load and validate the exact scan evidence approved for cleanup."""
    path = Path(path_value).expanduser().resolve(strict=True)
    try:
        report_bytes = path.read_bytes()
        actual_sha256 = hashlib.sha256(report_bytes).hexdigest()
        if actual_sha256 != expected_sha256:
            raise BatchScanError(
                "Approved scan report bytes do not match the SHA-256 accepted by the user."
            )
        report = json.loads(report_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BatchScanError(f"Approved scan report is unreadable: {path}: {exc}") from exc

    if not isinstance(report, dict) or report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise BatchScanError("Approved scan report has an unsupported schema.")
    if report.get("mode") != "scan" or report.get("completed") is not True:
        raise BatchScanError("Approved scan report must be a completed scan result.")
    report_scanner = report.get("scanner")
    if not isinstance(report_scanner, str) or os.path.normcase(report_scanner) != os.path.normcase(scanner):
        raise BatchScanError("Approved scan report used a different scanner executable.")

    target_items = report.get("targets")
    if not isinstance(target_items, list):
        raise BatchScanError("Approved scan report has no target findings.")
    approved: dict[str, dict[str, str]] = {}
    for item in target_items:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise BatchScanError("Approved scan report contains an invalid target entry.")
        target_path_object = _ensure_no_reparse_points(_lexical_path(item["path"]))
        target_path = str(target_path_object)
        infected = item.get("infected_before")
        hashes = item.get("infected_sha256_before")
        if not isinstance(infected, list) or not all(isinstance(value, str) for value in infected):
            raise BatchScanError(f"Approved scan report has an invalid infected list for {target_path}.")
        if not isinstance(hashes, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in hashes.items()
        ):
            raise BatchScanError(f"Approved scan report has invalid hashes for {target_path}.")
        normalized_infected = [str(_ensure_no_reparse_points(_lexical_path(value))) for value in infected]
        normalized_hashes = {
            str(_ensure_no_reparse_points(_lexical_path(key))): value for key, value in hashes.items()
        }
        if len(set(normalized_infected)) != len(normalized_infected):
            raise BatchScanError(f"Approved scan report has duplicate infection paths for {target_path}.")
        if set(normalized_infected) != set(normalized_hashes):
            raise BatchScanError(f"Approved scan report paths and hashes differ for {target_path}.")
        if any(len(value) != 64 or any(character not in "0123456789abcdef" for character in value) for value in hashes.values()):
            raise BatchScanError(f"Approved scan report has malformed SHA-256 values for {target_path}.")
        if target_path in approved:
            raise BatchScanError(f"Approved scan report contains a duplicate target: {target_path}")
        target_root = Path(target_path)
        if any(not _is_within(Path(value), target_root) for value in normalized_infected):
            raise BatchScanError(f"Approved scan report contains an out-of-target path for {target_path}.")
        approved[target_path] = normalized_hashes

    requested = {str(target) for target in targets}
    if set(approved) != requested:
        raise BatchScanError("Approved scan report targets differ from the requested cleanup targets.")
    return ApprovedScan(
        path=path,
        sha256=actual_sha256,
        findings=approved,
    )


def preflight_backups(files: Sequence[Path], backup_folder_name: str) -> dict[Path, dict[str, str]]:
    """Reject collisions, check space, and stage verified backups before mutation."""
    validate_backup_folder_name(backup_folder_name)
    records: dict[Path, dict[str, str]] = {}
    required_by_anchor: dict[str, int] = {}
    sample_by_anchor: dict[str, Path] = {}
    for source in files:
        backup_directory = _prepare_backup_directory(source, backup_folder_name, create=False)
        backup = backup_directory / source.name
        if os.path.lexists(backup):
            raise BatchScanError(f"Existing backup would be overwritten; move or preserve it first: {backup}")
        size = source.stat().st_size
        anchor = os.path.normcase(source.anchor or str(source.parent))
        required_by_anchor[anchor] = required_by_anchor.get(anchor, 0) + (size * 2)
        sample_by_anchor[anchor] = source.parent
        records[source] = {"path": str(backup), "source_sha256": sha256_file(source)}

    for anchor, required in required_by_anchor.items():
        free = shutil.disk_usage(sample_by_anchor[anchor]).free
        if free < required + MIN_FREE_BYTES:
            raise BatchScanError(
                f"Insufficient free space for backup and Maya save on {anchor}: "
                f"need at least {required + MIN_FREE_BYTES} bytes, have {free}."
            )
    for source, record in records.items():
        backup = Path(record["path"])
        backup_directory = _prepare_backup_directory(source, backup_folder_name, create=True)
        if backup.parent != backup_directory:
            raise BatchScanError(f"Backup destination changed during preflight: {backup}")
        _copy_backup_exclusive(source, backup)
        _prepare_backup_directory(source, backup_folder_name, create=False)
        try:
            if os.path.samefile(source, backup):
                backup.unlink()
                raise BatchScanError(f"Backup is not independent from its source scene: {backup}")
        except OSError as exc:
            try:
                backup.unlink()
            except OSError:
                pass
            raise BatchScanError(f"Unable to verify backup file identity: {backup}: {exc}") from exc
        if sha256_file(backup) != record["source_sha256"]:
            try:
                backup.unlink()
            except OSError:
                pass
            raise BatchScanError(f"Staged backup does not match the approved source bytes: {backup}")
    return records


def verify_backups(records: dict[Path, dict[str, str]]) -> list[dict[str, object]]:
    """Prove that every initially infected scene has a byte-identical backup."""
    verified: list[dict[str, object]] = []
    for source, record in records.items():
        backup = Path(record["path"])
        safe_backup = False
        try:
            backup_directory = _prepare_backup_directory(source, "_virus", create=False)
            safe_backup = (
                backup.parent == backup_directory
                and os.path.lexists(backup)
                and not _is_reparse_point(backup)
                and backup.is_file()
                and not os.path.samefile(source, backup)
            )
        except (BatchScanError, OSError):
            safe_backup = False
        actual_hash = sha256_file(backup) if safe_backup else None
        matches = actual_hash == record["source_sha256"]
        verified.append(
            {
                "source": str(source),
                "path": str(backup),
                "source_sha256": record["source_sha256"],
                "backup_sha256": actual_hash,
                "matches_source": matches,
            }
        )
    return verified


def build_report(
    mode: str,
    scanner: str,
    maya_version: str | None,
    backup_folder_name: str,
    results: Sequence[dict[str, object]],
) -> dict[str, object]:
    """Build the stable machine-readable batch result."""
    completed = all(item["status"] not in ("error", "skipped") for item in results)
    if mode == "scan":
        infection_free = completed and all(item["status"] == "clean" for item in results)
    else:
        infection_free = completed and all(not item.get("infected_after") for item in results)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "mode": mode,
        "scanner": scanner,
        "maya_version": maya_version,
        "backup_folder_name": backup_folder_name if mode == "clean" else None,
        "completed": completed,
        "infection_free": infection_free,
        "targets": list(results),
    }


def execute_batch(
    mode: str,
    scanner: str,
    targets: Sequence[Path],
    maya_version: str | None = None,
    confirmed: bool = False,
    backup_folder_name: str = "_virus",
    approved_findings: dict[str, dict[str, str]] | None = None,
    approved_scan_report: str | None = None,
    approved_report_sha256: str | None = None,
    runner: Runner = invoke_scanner,
) -> dict[str, object]:
    """Execute a serial scan or guarded cleanup batch."""
    if mode == "clean" and not confirmed:
        raise BatchScanError("Cleanup requires --confirm-clean after explicit user approval.")
    if mode == "clean" and approved_findings is None:
        raise BatchScanError("Cleanup requires a completed --approved-scan-report.")
    if mode == "clean" and not approved_scan_report:
        raise BatchScanError("Cleanup must pass the approved scan report to the scanner process.")
    if mode == "clean" and not approved_report_sha256:
        raise BatchScanError("Cleanup must bind the approved scan report content digest.")

    env = dict(os.environ)
    env["MAYA_UMBRELLA_IGNORE_BACKUP"] = "false"
    env["MAYA_UMBRELLA_BACKUP_FOLDER_NAME"] = backup_folder_name
    results: list[dict[str, object]] = []

    # Scan and hash the entire batch before any mutation. This prevents a late
    # target failure from leaving earlier targets already changed.
    for target in targets:
        item: dict[str, object] = {"path": str(target)}
        try:
            if mode == "clean":
                _ensure_no_reparse_points(target)
            infected_before = interpret_scan(runner(scanner, target, None, env, None, None), target)
            item["infected_before"] = [str(path) for path in infected_before]
            item["infected_sha256_before"] = hash_findings(infected_before)
            item["status"] = "infected" if infected_before else "clean"
        except (BatchScanError, OSError) as exc:
            item.update({"status": "error", "error": str(exc)})
        results.append(item)

    if mode == "scan":
        return build_report(mode, scanner, maya_version, backup_folder_name, results)

    if any(item["status"] == "error" for item in results):
        for item in results:
            if item["status"] != "error":
                item.update({"status": "skipped", "error": "Batch scan preflight failed before cleanup."})
        return build_report(mode, scanner, maya_version, backup_folder_name, results)

    for item in results:
        expected = approved_findings.get(item["path"])
        if expected is None or expected != item["infected_sha256_before"]:
            item.update(
                {
                    "status": "error",
                    "error": "Current infected paths or file hashes differ from the approved scan report.",
                }
            )
    if any(item["status"] == "error" for item in results):
        for item in results:
            if item["status"] != "error":
                item.update({"status": "skipped", "error": "Approval comparison failed before cleanup."})
        return build_report(mode, scanner, maya_version, backup_folder_name, results)

    if maya_version in {"2019", "2020", "2021"}:
        incompatible = [
            path
            for item in results
            for path in item["infected_before"]
            if not str(path).isascii()
        ]
        if incompatible:
            for index, item in enumerate(results):
                item.update(
                    {
                        "status": "error" if index == 0 else "skipped",
                        "error": (
                            "Maya 2019-2021 cleanup cannot safely open non-ASCII scene paths. "
                            "Rescan after choosing a supported Maya version or scope; do not move "
                            "or rename approved files."
                            if index == 0
                            else "Python 2 Maya path compatibility preflight failed."
                        ),
                    }
                )
            return build_report(mode, scanner, maya_version, backup_folder_name, results)

    all_infected = [Path(path) for item in results for path in item["infected_before"]]
    try:
        backup_records = preflight_backups(all_infected, backup_folder_name)
    except (BatchScanError, OSError) as exc:
        for index, item in enumerate(results):
            item.update(
                {
                    "status": "error" if index == 0 else "skipped",
                    "error": str(exc) if index == 0 else "Batch backup preflight failed before cleanup.",
                }
            )
        return build_report(mode, scanner, maya_version, backup_folder_name, results)

    stop_cleaning = False
    for item in results:
        if stop_cleaning:
            item.update(
                {
                    "status": "skipped",
                    "error": "A previous cleanup target failed.",
                    "backups": [],
                }
            )
            continue
        infected_before = [Path(path) for path in item["infected_before"]]
        if not infected_before:
            item.update({"status": "clean", "backups": []})
            continue

        failures = []
        try:
            _ensure_no_reparse_points(Path(item["path"]))
            cleanup = runner(
                scanner,
                Path(item["path"]),
                maya_version,
                env,
                approved_scan_report,
                approved_report_sha256,
            )
        except OSError as exc:
            cleanup = None
            failures.append(f"Maya cleanup could not start: {exc}")
        try:
            target_records = {source: backup_records[source] for source in infected_before}
            backup_results = verify_backups(target_records)
        except OSError as exc:
            backup_results = []
            failures.append(f"Backup verification failed: {exc}")
        item["backups"] = backup_results

        if cleanup is not None and cleanup.returncode != 0:
            details = (cleanup.stderr or cleanup.stdout).strip()
            failures.append(f"Maya cleanup exited with {cleanup.returncode}: {details}")
        if backup_results and any(not record["matches_source"] for record in backup_results):
            failures.append("One or more backups are missing or do not match the pre-clean source hash.")
        if failures:
            item.update({"status": "error", "error": " ".join(failures)})
            stop_cleaning = True
        else:
            item["status"] = "cleaned"

    # Verify the complete accepted scope only after every attempted mutation.
    # Initially clean and skipped targets are included so later cross-target
    # drift cannot be reported as an infection-free batch.
    for item in results:
        verification_failures = []
        target = Path(item["path"])
        try:
            if mode == "clean":
                _ensure_no_reparse_points(target)
            infected_after = interpret_scan(runner(scanner, target, None, env, None, None), target)
            item["infected_after"] = [str(path) for path in infected_after]
            if infected_after:
                verification_failures.append("Fresh verification still found infected files.")
        except (BatchScanError, OSError) as exc:
            item["infected_after"] = None
            verification_failures.append(f"Fresh verification scan failed: {exc}")
        if verification_failures:
            existing_error = item.get("error")
            item["error"] = " ".join(
                ([str(existing_error)] if existing_error else []) + verification_failures
            )
            if item["status"] != "skipped":
                item["status"] = "error"

    return build_report(mode, scanner, maya_version, backup_folder_name, results)


def prepare_report_path(path_value: str) -> Path:
    """Resolve and probe a report destination before cleanup can mutate scenes."""
    path = Path(path_value).expanduser().resolve(strict=False)
    if path.suffix.lower() != ".json":
        raise BatchScanError(f"Report destination must use a .json extension: {path}")
    if not path.parent.is_dir():
        raise BatchScanError(f"Report parent directory does not exist: {path.parent}")
    if os.path.lexists(path):
        raise BatchScanError(f"Report destination already exists; choose a fresh path: {path}")
    probe_source: Path | None = None
    probe_link: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{path.name}.probe-",
            dir=path.parent,
            delete=False,
        ) as stream:
            probe_source = Path(stream.name)
        probe_link = probe_source.with_name(f"{probe_source.name}.link")
        os.link(str(probe_source), str(probe_link))
    except OSError as exc:
        raise BatchScanError(
            f"Report directory cannot atomically publish a no-clobber report: {path.parent}: {exc}"
        ) from exc
    finally:
        for probe in (probe_link, probe_source):
            if probe:
                try:
                    probe.unlink(missing_ok=True)
                except OSError:
                    pass
    return path


def write_report(path: Path, report: dict[str, object]) -> str:
    """Publish exact report bytes atomically and return their SHA-256 digest."""
    payload = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            temporary = Path(stream.name)
        os.link(str(temporary), str(path))
        return payload_sha256
    finally:
        if temporary:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    try:
        cleaning = args.mode == "clean"
        scanner = resolve_scanner(args.scanner)
        targets = normalize_targets(args.paths, cleaning=cleaning)
        backup_folder = validate_backup_folder_name("_virus")
        approved_scan_report = getattr(args, "approved_scan_report", None)
        approved_report_sha256 = getattr(args, "approved_scan_report_sha256", None)
        report_path = prepare_report_path(args.report) if args.report else None
        if approved_scan_report and report_path:
            approved_path = Path(approved_scan_report).expanduser().resolve(strict=True)
            if os.path.normcase(str(approved_path)) == os.path.normcase(str(report_path)):
                raise BatchScanError("Cleanup report must not overwrite its approved scan report.")
        approved_scan = (
            load_approved_scan(
                approved_scan_report,
                approved_report_sha256,
                scanner,
                targets,
            )
            if approved_scan_report
            else None
        )
        report = execute_batch(
            mode=args.mode,
            scanner=scanner,
            targets=targets,
            maya_version=getattr(args, "maya_version", None),
            confirmed=getattr(args, "confirm_clean", False),
            backup_folder_name=backup_folder,
            approved_findings=approved_scan.findings if approved_scan else None,
            approved_scan_report=str(approved_scan.path) if approved_scan else None,
            approved_report_sha256=approved_scan.sha256 if approved_scan else None,
        )
        if approved_scan:
            report["approved_scan_report"] = str(approved_scan.path)
            report["approved_scan_report_sha256"] = approved_scan.sha256
        if report_path:
            try:
                report_file_sha256 = write_report(report_path, report)
                if args.mode == "scan":
                    report["report_file_sha256"] = report_file_sha256
            except OSError as exc:
                report["completed"] = False
                report["infection_free"] = False
                report["report_write_error"] = str(exc)
                print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
                return 2
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["completed"] else 1
    except (BatchScanError, OSError) as exc:
        error_report = {"schema_version": REPORT_SCHEMA_VERSION, "completed": False, "error": str(exc)}
        print(json.dumps(error_report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
