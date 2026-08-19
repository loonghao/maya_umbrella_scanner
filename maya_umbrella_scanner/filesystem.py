# Import built-in modules
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import mkdtemp

# Import third-party modules
from maya_umbrella.signatures import FILE_VIRUS_SIGNATURES
from maya_umbrella.signatures import JOB_SCRIPTS_VIRUS_SIGNATURES


class VirusScanError(RuntimeError):
    """Raised when the signature scanner cannot complete reliably."""


MAYA_STARTUP_PATH_VARIABLES = (
    "MAYA_ENV_DIR",
    "MAYA_MODULE_PATH",
    "MAYA_PLUG_IN_PATH",
    "MAYA_SCRIPT_PATH",
    "MAYA_SHELF_PATH",
    "PYTHONHOME",
    "PYTHONPATH",
)

MAYA_UMBRELLA_SAFE_ENVIRONMENT = {
    "MAYA_UMBRELLA_BACKUP_FOLDER_NAME": "_virus",
    "MAYA_UMBRELLA_DISABLE_ALL_HOOKS": "true",
    "MAYA_UMBRELLA_DISABLE_HOOKS": "",
    "MAYA_UMBRELLA_IGNORE_BACKUP": "false",
    "MAYA_UMBRELLA_LOG_LEVEL": "INFO",
    "MAYA_UMBRELLA_LOG_NAME": "maya_umbrella_scanner",
}


def this_root():
    """Returns the root directory of the current Maya installation.

    Returns:
        str: The root directory of the current Maya installation.
    """
    path = sys.executable
    if "maya_umbrella.exe" in path:
        return os.path.dirname(path)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def validate_backup_folder_name(value):
    """Reserve one fixed quarantine name so arbitrary project trees cannot be hidden."""
    if value != "_virus":
        raise VirusScanError("MAYA_UMBRELLA_BACKUP_FOLDER_NAME must remain the reserved value _virus.")
    return value


def get_rg_exe():
    """Assembles the path to the rg (ripgrep) executable.

    Returns:
        str: The path to the rg executable.
    """
    root = this_root()
    return os.path.join(root, "bin", "rg.exe")


def assemble_rg_varius_check_commands(path):
    """Assemble the command to check for viruses in the given path.

    Args:
        path (str): The path to check for viruses.

    Returns:
        str: The command to check for viruses in the given path.
    """
    rg = get_rg_exe()
    signatures = JOB_SCRIPTS_VIRUS_SIGNATURES + FILE_VIRUS_SIGNATURES
    signatures = list(set(signatures))
    backup_folder_name = validate_backup_folder_name(os.getenv("MAYA_UMBRELLA_BACKUP_FOLDER_NAME", "_virus"))
    cmd = [
        rg,
        "-l",
        "|".join(signatures),
        path,
        "--binary",
        "--sort-files",
        "-g",
        "*.m[ab]",
        "-g",
        # Ignore backup files without allowing environment text to become a glob.
        f"!**/{backup_folder_name}/**",
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, check=False)
    except OSError as exc:
        raise VirusScanError(f"Unable to start signature scanner: {exc}") from exc

    # ripgrep uses 0 for matches, 1 for no matches, and >=2 for actual errors.
    if completed.returncode == 1:
        return
    if completed.returncode != 0:
        details = completed.stderr.decode("utf-8", errors="replace").strip()
        message = f"Signature scan failed with exit code {completed.returncode}"
        if details:
            message = f"{message}: {details}"
        raise VirusScanError(message)

    files = completed.stdout
    if not files:
        raise VirusScanError("Signature scanner reported matches but returned no file list.")

    infected_file = os.path.join(mkdtemp("maya-umbrella"), "infected_file.txt")
    with open(infected_file, "wb") as f:
        f.write(files)
    return infected_file


def _sha256_file(path):
    """Return the SHA-256 digest for one scene file."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_path(value):
    """Normalize an absolute path without following a newly introduced redirect."""
    return os.path.normcase(os.path.abspath(os.path.expanduser(value)))


def _is_reparse_point(path):
    """Return whether one existing path component can redirect filesystem access."""
    try:
        status = os.lstat(path)
    except OSError as exc:
        raise VirusScanError(f"Approved path component cannot be inspected: {path}: {exc}") from exc
    attributes = getattr(status, "st_file_attributes", 0)
    return os.path.islink(path) or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def validate_cleanup_path(value):
    """Reject approval paths whose current components contain symlinks or junctions."""
    normalized = Path(_normalized_path(value))
    for component in reversed((normalized, *normalized.parents)):
        if str(component) == component.anchor:
            continue
        if _is_reparse_point(component):
            raise VirusScanError(f"Approved cleanup path contains a symlink or junction: {component}")
    return str(normalized)


def _manifest_entries(infected_file):
    """Read and normalize the scanner's newline-delimited manifest."""
    if not infected_file:
        return []
    with open(infected_file, "rb") as stream:
        return [_normalized_path(line.decode("utf-8-sig", errors="replace").strip()) for line in stream if line.strip()]


def verify_approved_scan_report(report_path, report_sha256, target, infected_file):
    """Bind cleanup to the exact paths and hashes in a completed Skill scan."""
    try:
        with open(report_path, "rb") as stream:
            report_bytes = stream.read()
        actual_report_sha256 = hashlib.sha256(report_bytes).hexdigest()
        if actual_report_sha256 != report_sha256:
            raise VirusScanError("Approved scan report content changed after helper validation.")
        report = json.loads(report_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VirusScanError(f"Approved scan report is unreadable: {report_path}: {exc}") from exc

    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise VirusScanError("Approved scan report has an unsupported schema.")
    if report.get("mode") != "scan" or report.get("completed") is not True:
        raise VirusScanError("Approved scan report must be a completed scan result.")

    normalized_target = validate_cleanup_path(target)
    target_items = report.get("targets")
    if not isinstance(target_items, list):
        raise VirusScanError("Approved scan report has no target findings.")
    matching_targets = [
        item
        for item in target_items
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and _normalized_path(item["path"]) == normalized_target
    ]
    if len(matching_targets) != 1:
        raise VirusScanError("Approved scan report must contain the cleanup target exactly once.")

    expected = matching_targets[0].get("infected_sha256_before")
    infected_before = matching_targets[0].get("infected_before")
    if not isinstance(infected_before, list) or not all(isinstance(path, str) for path in infected_before):
        raise VirusScanError("Approved scan report has an invalid infection list.")
    if not isinstance(expected, dict) or not all(
        isinstance(path, str) and isinstance(digest, str) for path, digest in expected.items()
    ):
        raise VirusScanError("Approved scan report has invalid infection hashes.")
    if set(infected_before) != set(expected):
        raise VirusScanError("Approved infection paths and hashes differ.")

    normalized_expected = {}
    target_prefix = normalized_target + os.sep
    for path, digest in expected.items():
        normalized_path = validate_cleanup_path(path)
        if normalized_path != normalized_target and not normalized_path.startswith(target_prefix):
            raise VirusScanError(f"Approved infection path escaped the cleanup target: {path}")
        if normalized_path in normalized_expected:
            raise VirusScanError(f"Approved scan report contains a duplicate infection path: {path}")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise VirusScanError(f"Approved scan report has a malformed SHA-256 value: {path}")
        normalized_expected[normalized_path] = digest

    current_paths = _manifest_entries(infected_file)
    for path in current_paths:
        validate_cleanup_path(path)
    if len(set(current_paths)) != len(current_paths):
        raise VirusScanError("Current infection manifest contains duplicate paths.")
    if set(current_paths) != set(normalized_expected):
        raise VirusScanError("Current infected paths differ from the approved scan report.")
    try:
        current_hashes = {path: _sha256_file(path) for path in current_paths}
    except OSError as exc:
        raise VirusScanError(f"Unable to hash a currently infected scene: {exc}") from exc
    if current_hashes != normalized_expected:
        raise VirusScanError("Current infected file hashes differ from the approved scan report.")


def isolated_maya_environment(maya_python, maya_app_dir):
    """Build a Maya environment that cannot load the user's startup scripts."""
    os.makedirs(maya_app_dir, exist_ok=True)
    maya_env_file = os.path.join(os.path.abspath(maya_app_dir), "Maya.env")
    try:
        with open(maya_env_file, "x", encoding="utf-8"):
            pass
    except FileExistsError as exc:
        if os.path.islink(maya_env_file) or not os.path.isfile(maya_env_file) or os.path.getsize(maya_env_file):
            raise VirusScanError(f"Maya isolation directory contains an unsafe Maya.env: {maya_env_file}") from exc
    env = dict(os.environ)
    for variable in MAYA_STARTUP_PATH_VARIABLES:
        env.pop(variable, None)
    for variable in tuple(env):
        if variable.upper().startswith("MAYA_UMBRELLA_"):
            env.pop(variable)
    env["MAYA_LOCATION"] = os.path.dirname(os.path.dirname(os.path.abspath(maya_python)))
    env["MAYA_APP_DIR"] = os.path.abspath(maya_app_dir)
    env["MAYA_ENV_DIR"] = os.path.abspath(maya_app_dir)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONPATH"] = os.path.join(this_root(), "lib", "site-packages")
    env.update(MAYA_UMBRELLA_SAFE_ENVIRONMENT)
    env["MAYA_UMBRELLA_LOG_ROOT"] = os.path.join(os.path.abspath(maya_app_dir), "logs")
    return env


def run_maya_cleanup(
    maya_python,
    run_maya_py,
    infected_file,
    approved_scan_report,
    approved_report_sha256,
    target,
    maya_app_dir,
):
    """Run Maya Python with an argument vector and return its process exit code.

    Args:
        maya_python (str): Path to the Maya's Python interpreter.
        run_maya_py (str): Path to the Python script to run within Maya's Python interpreter.
        infected_file (str): Path to the file to be scanned for viruses.
        approved_scan_report (str): Exact scan report accepted by the user.
        approved_report_sha256 (str): User-accepted digest of the report bytes.
        target (str): Exact target directory bound by the report.
        maya_app_dir (str): Empty temporary Maya application directory.

    Returns:
        int: The Maya Python process exit code.
    """
    if not os.path.isfile(maya_python):
        raise FileNotFoundError(f"Maya Python not found: {maya_python}")
    env = isolated_maya_environment(maya_python, maya_app_dir)
    completed = subprocess.run(
        [
            maya_python,
            "-s",
            run_maya_py,
            infected_file,
            approved_scan_report,
            approved_report_sha256,
            target,
        ],
        env=env,
        check=False,
    )
    return completed.returncode
