# Import future modules
from __future__ import annotations

# Import built-in modules
import argparse
from collections.abc import Iterator
import os
from pathlib import Path
import shutil
import stat
import subprocess
from typing import TYPE_CHECKING
import zipfile

# Import third-party modules
from nox_actions.utils import PACKAGE_NAME
from nox_actions.utils import THIS_ROOT

# Import local modules
from maya_umbrella_scanner.__version__ import __version__


if TYPE_CHECKING:
    # Import third-party modules
    import nox


REPRODUCIBLE_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
REPRODUCIBLE_FILE_ATTRIBUTES = (stat.S_IFREG | 0o644) << 16


def write_reproducible_zip(source_root: Path, destination: Path) -> None:
    """Archive files with stable paths, ordering, timestamps, and attributes."""
    root = Path(source_root)
    members = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    with zipfile.ZipFile(destination, "w") as archive:
        for source in members:
            info = zipfile.ZipInfo(
                source.relative_to(root).as_posix(),
                date_time=REPRODUCIBLE_ZIP_TIMESTAMP,
            )
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = REPRODUCIBLE_FILE_ATTRIBUTES
            info.file_size = source.stat().st_size
            with source.open("rb") as input_stream, archive.open(info, "w") as output_stream:
                shutil.copyfileobj(input_stream, output_stream)


def make_install_zip(session: nox.Session) -> None:
    temp_dir = os.path.join(THIS_ROOT, ".zip")
    build_root = os.path.join(temp_dir, "maya_umbrella")
    script_dir = os.path.join(build_root, "scripts")
    shutil.rmtree(temp_dir, ignore_errors=True)
    bat_template = """
@echo off
SET "batPath=%~dp0"
SET "modContent=+ maya_umbrella {version} %batPath%"
SET "modFilePath=%~dp0maya_umbrella.mod"
echo %modContent% > "%modFilePath%"
xcopy "%~dp0maya_umbrella.mod"  "%USERPROFILE%\\documents\\maya\\modules\\" /y
del  /f "%~dp0maya_umbrella.mod"
pause
"""
    parser = argparse.ArgumentParser(prog="nox -s make-zip")
    parser.add_argument("--version", required=True, help="Version to use for the zip file")
    args = parser.parse_args(session.posargs)
    version = str(args.version)
    print(f"make zip to current version: {version}")

    shutil.copytree(os.path.join(THIS_ROOT, "maya_umbrella"),
                    os.path.join(script_dir, "maya_umbrella"))
    with open(os.path.join(build_root, "install.bat"), "w") as f:
        f.write(bat_template.format(version=version))

    shutil.copy2(os.path.join(THIS_ROOT, "maya", "userSetup.py"),
                 os.path.join(script_dir, "userSetup.py"))

    zip_file = os.path.join(temp_dir, f"{PACKAGE_NAME}-{version}.zip")
    with zipfile.ZipFile(zip_file, "w") as zip_obj:
        for root, _, files in os.walk(build_root):
            for file in files:
                zip_obj.write(os.path.join(root, file),
                              os.path.relpath(os.path.join(root, file),
                                              os.path.join(build_root, ".")))
    print("Saving to {zipfile}".format(zipfile=zip_file))


# https://github.com/pypa/pip/blob/main/noxfile.py#L185C1-L250C59@nox.session
def vendoring(session: nox.Session) -> None:
    session.install("vendoring~=1.2.0")

    parser = argparse.ArgumentParser(prog="nox -s vendoring")
    parser.add_argument("--upgrade-all", action="store_true")
    parser.add_argument("--upgrade", action="append", default=[])
    parser.add_argument("--skip", action="append", default=[])
    args = parser.parse_args(session.posargs)

    if not (args.upgrade or args.upgrade_all):
        session.run("vendoring", "sync", "-v")
        return

    def pinned_requirements(path: Path) -> Iterator[tuple[str, str]]:
        for line in path.read_text().splitlines(keepends=False):
            one, sep, two = line.partition("==")
            if not sep:
                continue
            name = one.strip()
            version = two.split("#", 1)[0].strip()
            if name and version:
                yield name, version

    vendor_txt = Path("maya_umbrella/_vendor/vendor.txt")
    for name, old_version in pinned_requirements(vendor_txt):
        if name in args.skip:
            continue
        if args.upgrade and name not in args.upgrade:
            continue

        # update requirements.txt
        session.run("vendoring", "update", ".", name)

        # get the updated version
        new_version = old_version
        for inner_name, inner_version in pinned_requirements(vendor_txt):
            if inner_name == name:
                # this is a dedicated assignment, to make lint happy
                new_version = inner_version
                break
        else:
            session.error(f"Could not find {name} in {vendor_txt}")

        # check if the version changed.
        if new_version == old_version:
            continue  # no change, nothing more to do here.

        # synchronize the contents
        session.run("vendoring", "sync", ".")


def build_exe(session: nox.Session) -> None:
    parser = argparse.ArgumentParser(prog="nox -s build-exe --release")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--version", help="Version to use for the zip file")
    args = parser.parse_args(session.posargs)
    if args.release and not args.version:
        parser.error("--version is required with --release")
    build_root = os.path.join(THIS_ROOT, "build", "x86_64-pc-windows-msvc", "release", "install")
    session.install("pyoxidizer==0.24.0")
    session.run("pyoxidizer", "build", "install", "--path", THIS_ROOT, "--release")
    shutil.copytree(os.path.join(THIS_ROOT, "bin"), os.path.join(build_root, "bin"))
    site_packages = Path(build_root, "lib", "site-packages")
    expected_distributions = {
        "maya_umbrella": "0.18.0",
        "click": "8.1.7",
        "colorama": "0.4.6",
    }
    for distribution, version in expected_distributions.items():
        actual = sorted(path.name for path in site_packages.glob(f"{distribution}-*.dist-info"))
        expected = [f"{distribution}-{version}.dist-info"]
        if actual != expected:
            session.error(f"Expected bundled distribution {expected}, found {actual}")
    executable = Path(build_root, "maya_umbrella.exe")
    version_result = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False)
    if version_result.returncode or version_result.stdout.strip() != f"maya-umbrella-scanner {__version__}":
        session.error("Built scanner does not report the package version.")
    scan_help = subprocess.run([executable, "scan", "--help"], capture_output=True, text=True, check=False)
    if scan_help.returncode or not {"--path", "--report"}.issubset(scan_help.stdout.split()):
        session.error("Built scanner does not expose the portable batch scan contract.")
    clean_help = subprocess.run([executable, "clean", "--help"], capture_output=True, text=True, check=False)
    if clean_help.returncode or not {
        "--approved-scan-report",
        "--approved-scan-report-sha256",
        "--confirm-clean",
        "--maya-version",
    }.issubset(clean_help.stdout.split()):
        session.error("Built scanner does not expose the guarded batch cleanup contract.")
    if args.release:
        temp_dir = os.path.join(THIS_ROOT, ".zip")
        shutil.rmtree(temp_dir, ignore_errors=True)
        version = str(args.version)
        print(f"make zip to current version: {version}")
        os.makedirs(temp_dir, exist_ok=True)
        zip_file = os.path.join(temp_dir, f"{PACKAGE_NAME}-{version}.zip")
        write_reproducible_zip(Path(build_root), Path(zip_file))
        print("Saving to {zipfile}".format(zipfile=zip_file))
