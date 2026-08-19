# Import built-in modules
import argparse
import os
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

# Import third-party modules
import click
from maya_umbrella.filesystem import get_maya_install_root

# Import local modules
from maya_umbrella_scanner.__version__ import __version__
from maya_umbrella_scanner.filesystem import VirusScanError
from maya_umbrella_scanner.filesystem import assemble_rg_varius_check_commands
from maya_umbrella_scanner.filesystem import isolated_maya_environment
from maya_umbrella_scanner.filesystem import run_maya_cleanup
from maya_umbrella_scanner.filesystem import validate_cleanup_path
from maya_umbrella_scanner.filesystem import verify_approved_scan_report
from maya_umbrella_scanner.template import RUNNER_TEMPLATE


def _query_maya_year(maya_python):
    """Ask a selected mayapy executable for its actual Maya release year."""
    version_script = "import maya.standalone; maya.standalone.initialize(); from maya import cmds; print('MAYA_UMBRELLA_VERSION=' + str(cmds.about(version=True))); maya.standalone.uninitialize()"
    with TemporaryDirectory(prefix="maya-umbrella-version-") as maya_app_dir:
        env = isolated_maya_environment(maya_python, maya_app_dir)
        try:
            completed = subprocess.run(
                [
                    maya_python,
                    "-s",
                    "-c",
                    version_script,
                ],
                capture_output=True,
                text=True,
                errors="replace",
                env=env,
                check=False,
            )
        except OSError as exc:
            raise click.ClickException(f"Unable to query Maya version from {maya_python}: {exc}") from exc
    if completed.returncode:
        details = (completed.stderr or completed.stdout).strip()
        raise click.ClickException(
            f"Unable to query Maya version from {maya_python} (exit {completed.returncode}): {details}"
        )
    for line in reversed(completed.stdout.splitlines()):
        match = re.fullmatch(r"MAYA_UMBRELLA_VERSION=(20\d{2})(?:\..*)?", line.strip())
        if match:
            return match.group(1)
    raise click.ClickException(f"Mayapy did not report a recognizable Maya year: {maya_python}")


def resolve_maya_python(maya_version):
    """Resolve and prove the mayapy executable for the requested Maya year."""
    configured_root = os.environ.pop("MAYA_LOCATION", None)
    try:
        registered_root = get_maya_install_root(maya_version)
    finally:
        if configured_root is not None:
            os.environ["MAYA_LOCATION"] = configured_root

    candidates = []
    for root in (registered_root, configured_root):
        if root and os.path.normcase(os.path.abspath(root)) not in {
            os.path.normcase(os.path.abspath(value)) for value in candidates
        }:
            candidates.append(root)
    failures = []
    for root in candidates:
        maya_python = os.path.join(root, "bin", "mayapy.exe")
        if not os.path.isfile(maya_python):
            failures.append(f"mayapy.exe not found under {root}")
            continue
        try:
            actual_year = _query_maya_year(maya_python)
        except click.ClickException as exc:
            failures.append(str(exc))
            continue
        if actual_year == maya_version:
            return maya_python
        failures.append(f"{maya_python} reports Maya {actual_year}, not requested Maya {maya_version}")
    details = "; ".join(failures) if failures else "no registered or configured installation was found"
    raise click.ClickException(f"Maya {maya_version} could not be bound to an exact mayapy.exe: {details}")


def main(argv=None):
    """Run the portable batch CLI or the backward-compatible single-root interface."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in {"scan", "clean"}:
        # Import lazily so legacy invocations keep their existing startup path.
        # Import local modules
        from maya_umbrella_scanner.batch_cli import main as batch_main

        raise SystemExit(batch_main(arguments))

    args = argparse.ArgumentParser(
        description="Portable Maya scene antivirus scanner",
        epilog=(
            "For guarded batch operations use: maya_umbrella scan --help "
            "or maya_umbrella clean --help"
        ),
    )
    args.add_argument(
        "--version",
        action="version",
        version=f"maya-umbrella-scanner {__version__}",
    )
    args.add_argument("--maya-version", type=str)
    args.add_argument("--path", type=str, required=True)
    args.add_argument(
        "--approved-scan-report",
        type=str,
        help="Completed Agent Skill scan report used to bind cleanup to approved files",
    )
    args.add_argument(
        "--approved-scan-report-sha256",
        type=str,
        help="SHA-256 of the approved report content validated by the Agent Skill",
    )
    options = args.parse_args(arguments)
    if bool(options.approved_scan_report) != bool(options.approved_scan_report_sha256):
        raise click.ClickException(
            "--approved-scan-report and --approved-scan-report-sha256 must be provided together."
        )
    if options.approved_scan_report_sha256 and (
        len(options.approved_scan_report_sha256) != 64
        or any(character not in "0123456789abcdef" for character in options.approved_scan_report_sha256)
    ):
        raise click.ClickException("--approved-scan-report-sha256 must be a lowercase SHA-256 value.")
    if options.maya_version and not re.fullmatch(r"20\d{2}", options.maya_version):
        raise click.ClickException("--maya-version must be a four-digit Maya release year.")
    if not os.path.exists(options.path):
        raise click.ClickException(f"Path does not exist: {options.path}")
    if options.maya_version:
        try:
            validate_cleanup_path(options.path)
        except VirusScanError as exc:
            raise click.ClickException(f"Cleanup target validation failed: {exc}") from exc
    try:
        infected_file = assemble_rg_varius_check_commands(options.path)
    except VirusScanError as exc:
        raise click.ClickException(str(exc)) from exc
    if not infected_file:
        click.echo("No infected files found.")
        sys.exit(0)
    if options.maya_version:
        if os.getenv("MAYA_UMBRELLA_IGNORE_BACKUP", "false").lower() == "true":
            raise click.ClickException("Refusing to clean while MAYA_UMBRELLA_IGNORE_BACKUP=true.")
        if not options.approved_scan_report:
            raise click.ClickException("Cleanup requires an approved scan report and its user-accepted SHA-256.")
        try:
            verify_approved_scan_report(
                options.approved_scan_report,
                options.approved_scan_report_sha256,
                options.path,
                infected_file,
            )
        except VirusScanError as exc:
            raise click.ClickException(f"Cleanup approval verification failed: {exc}") from exc
        maya_python = resolve_maya_python(options.maya_version)
        click.echo(f"Loading maya... {maya_python}")
        with TemporaryDirectory() as temp_dir:
            run_maya_py = os.path.join(temp_dir, "run_maya.py")
            with open(run_maya_py, "w", encoding="utf-8") as f:
                f.write(RUNNER_TEMPLATE)
            try:
                maya_app_dir = os.path.join(temp_dir, "maya-app")
                return_code = run_maya_cleanup(
                    maya_python,
                    run_maya_py,
                    infected_file,
                    options.approved_scan_report,
                    options.approved_scan_report_sha256,
                    options.path,
                    maya_app_dir,
                )
            except OSError as exc:
                raise click.ClickException(f"Maya cleanup could not start: {exc}") from exc
        if return_code:
            raise click.ClickException(f"Maya cleanup failed with exit code {return_code}.")
        try:
            validate_cleanup_path(options.path)
            remaining_infected_file = assemble_rg_varius_check_commands(options.path)
        except VirusScanError as exc:
            raise click.ClickException(f"Cleanup verification failed: {exc}") from exc
        if remaining_infected_file:
            raise click.ClickException(
                f"Cleanup verification found remaining infected files: {remaining_infected_file}"
            )
        click.echo("Cleaning completed and verification found no remaining signatures.")
    else:
        click.echo(f"Export infected files to: {infected_file}")
