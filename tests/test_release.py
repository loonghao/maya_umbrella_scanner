"""Release artifact reproducibility tests."""

# Import built-in modules
import hashlib
import os
from pathlib import Path
import stat
import zipfile

# Import third-party modules
from nox_actions.release import write_reproducible_zip


def test_reproducible_zip_ignores_source_mtime(tmp_path: Path):
    payload = tmp_path / "payload"
    module = payload / "lib" / "site-packages" / "scanner.py"
    executable = payload / "maya_umbrella.exe"
    module.parent.mkdir(parents=True)
    module.write_bytes(b"scanner module\n")
    executable.write_bytes(b"portable executable\n")
    for source in (module, executable):
        os.utime(source, (1_700_000_000, 1_700_000_000))

    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    write_reproducible_zip(payload, first)

    for source in (module, executable):
        os.utime(source, (1_700_000_010, 1_700_000_010))
    write_reproducible_zip(payload, second)

    first_bytes = first.read_bytes()
    second_bytes = second.read_bytes()
    assert first_bytes == second_bytes
    assert hashlib.sha256(first_bytes).digest() == hashlib.sha256(second_bytes).digest()

    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["lib/site-packages/scanner.py", "maya_umbrella.exe"]
        for info in archive.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.create_system == 3
            assert info.external_attr == (stat.S_IFREG | 0o644) << 16
