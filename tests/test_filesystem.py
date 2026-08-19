"""Tests for fail-closed scanner process handling."""

# Import built-in modules
import json
import os
import subprocess

# Import third-party modules
import pytest

# Import local modules
from maya_umbrella_scanner import filesystem


def test_no_ripgrep_matches_is_clean(monkeypatch):
    completed = subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"")
    monkeypatch.setattr(filesystem.subprocess, "run", lambda *args, **kwargs: completed)

    assert filesystem.assemble_rg_varius_check_commands("C:/scenes") is None


def test_ripgrep_failure_is_not_reported_as_clean(monkeypatch):
    completed = subprocess.CompletedProcess([], 2, stdout=b"", stderr=b"access denied")
    monkeypatch.setattr(filesystem.subprocess, "run", lambda *args, **kwargs: completed)

    with pytest.raises(filesystem.VirusScanError, match="exit code 2.*access denied"):
        filesystem.assemble_rg_varius_check_commands("C:/scenes")


def test_matches_are_written_to_manifest(monkeypatch, tmp_path):
    completed = subprocess.CompletedProcess([], 0, stdout=b"C:/scenes/infected.ma\r\n", stderr=b"")
    monkeypatch.setattr(filesystem.subprocess, "run", lambda *args, **kwargs: completed)
    monkeypatch.setattr(filesystem, "mkdtemp", lambda suffix: str(tmp_path))

    manifest = filesystem.assemble_rg_varius_check_commands("C:/scenes")

    assert manifest == str(tmp_path / "infected_file.txt")
    assert (tmp_path / "infected_file.txt").read_bytes() == completed.stdout


def test_backup_folder_glob_metacharacters_are_rejected(monkeypatch):
    monkeypatch.setenv("MAYA_UMBRELLA_BACKUP_FOLDER_NAME", "*")

    with pytest.raises(filesystem.VirusScanError, match="reserved value _virus"):
        filesystem.assemble_rg_varius_check_commands("C:/scenes")


@pytest.mark.parametrize("name", ["NUL", "con.txt", "AUX", "foo.", "...", "a" * 256])
def test_backup_folder_rejects_unsafe_windows_components(monkeypatch, name):
    monkeypatch.setenv("MAYA_UMBRELLA_BACKUP_FOLDER_NAME", name)

    with pytest.raises(filesystem.VirusScanError, match="reserved value _virus"):
        filesystem.assemble_rg_varius_check_commands("C:/scenes")


def test_backup_folder_cannot_hide_existing_project_tree(monkeypatch):
    monkeypatch.setenv("MAYA_UMBRELLA_BACKUP_FOLDER_NAME", "assets")

    with pytest.raises(filesystem.VirusScanError, match="reserved value _virus"):
        filesystem.assemble_rg_varius_check_commands("C:/scenes")


def test_maya_cleanup_uses_argv_for_special_paths(monkeypatch, tmp_path):
    maya_python = tmp_path / "Maya 2024 %测试" / "bin" / "mayapy.exe"
    maya_python.parent.mkdir(parents=True)
    maya_python.touch()
    runner = tmp_path / "run script %.py"
    runner.touch()
    manifest = tmp_path / "感染 list %.txt"
    manifest.touch()
    maya_app_dir = tmp_path / "isolated maya app"
    captured = {}
    monkeypatch.setenv("MAYA_SCRIPT_PATH", str(tmp_path / "malicious scripts"))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "malicious python"))
    monkeypatch.setenv("MAYA_UMBRELLA_LOG_ROOT", str(tmp_path / "outside logs"))
    monkeypatch.setenv("MAYA_UMBRELLA_LOG_NAME", "attacker-controlled")
    monkeypatch.setenv("MAYA_UMBRELLA_FUTURE_SWITCH", "unsafe")

    def run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(filesystem.subprocess, "run", run)

    return_code = filesystem.run_maya_cleanup(
        maya_python=str(maya_python),
        run_maya_py=str(runner),
        infected_file=str(manifest),
        approved_scan_report=str(tmp_path / "approved.json"),
        approved_report_sha256="a" * 64,
        target=str(tmp_path / "scenes"),
        maya_app_dir=str(maya_app_dir),
    )

    assert return_code == 7
    assert captured["command"] == [
        str(maya_python),
        "-s",
        str(runner),
        str(manifest),
        str(tmp_path / "approved.json"),
        "a" * 64,
        str(tmp_path / "scenes"),
    ]
    assert captured["kwargs"]["check"] is False
    assert "shell" not in captured["kwargs"]
    assert captured["kwargs"]["env"]["MAYA_APP_DIR"] == str(maya_app_dir)
    assert captured["kwargs"]["env"]["MAYA_ENV_DIR"] == str(maya_app_dir)
    assert captured["kwargs"]["env"]["PYTHONNOUSERSITE"] == "1"
    assert captured["kwargs"]["env"]["MAYA_LOCATION"] == str(maya_python.parents[1])
    assert captured["kwargs"]["env"]["MAYA_UMBRELLA_BACKUP_FOLDER_NAME"] == "_virus"
    assert captured["kwargs"]["env"]["MAYA_UMBRELLA_DISABLE_ALL_HOOKS"] == "true"
    assert captured["kwargs"]["env"]["MAYA_UMBRELLA_IGNORE_BACKUP"] == "false"
    assert captured["kwargs"]["env"]["MAYA_UMBRELLA_LOG_LEVEL"] == "INFO"
    assert captured["kwargs"]["env"]["MAYA_UMBRELLA_LOG_NAME"] == "maya_umbrella_scanner"
    assert captured["kwargs"]["env"]["MAYA_UMBRELLA_LOG_ROOT"] == str(maya_app_dir / "logs")
    assert "MAYA_UMBRELLA_FUTURE_SWITCH" not in captured["kwargs"]["env"]
    assert (maya_app_dir / "Maya.env").read_bytes() == b""
    assert "MAYA_SCRIPT_PATH" not in captured["kwargs"]["env"]
    assert str(tmp_path / "malicious python") not in captured["kwargs"]["env"]["PYTHONPATH"]


def test_maya_isolation_rejects_existing_nonempty_environment(tmp_path):
    maya_python = tmp_path / "Maya2024" / "bin" / "mayapy.exe"
    maya_python.parent.mkdir(parents=True)
    maya_python.touch()
    maya_app_dir = tmp_path / "maya-app"
    maya_app_dir.mkdir()
    (maya_app_dir / "Maya.env").write_text("MAYA_SCRIPT_PATH=malicious", encoding="utf-8")

    with pytest.raises(filesystem.VirusScanError, match="unsafe Maya.env"):
        filesystem.isolated_maya_environment(str(maya_python), str(maya_app_dir))


def test_cleanup_path_rejects_reparse_component(monkeypatch, tmp_path):
    target = tmp_path / "approved"
    target.mkdir()
    monkeypatch.setattr(
        filesystem,
        "_is_reparse_point",
        lambda path: os.path.normcase(str(path)) == os.path.normcase(str(target)),
    )

    with pytest.raises(filesystem.VirusScanError, match="symlink or junction"):
        filesystem.validate_cleanup_path(str(target))


def test_approved_report_detects_file_hash_drift(tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"approved bytes")
    manifest = tmp_path / "infected.txt"
    manifest.write_text(f"{infected}\n", encoding="utf-8")
    report = tmp_path / "approved.json"
    expected_hash = filesystem._sha256_file(infected)
    report.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "scan",
                "completed": True,
                "targets": [
                    {
                        "path": str(target),
                        "infected_before": [str(infected)],
                        "infected_sha256_before": {str(infected): expected_hash},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report_bytes = report.read_bytes()
    report_sha256 = filesystem.hashlib.sha256(report_bytes).hexdigest()
    filesystem.verify_approved_scan_report(str(report), report_sha256, str(target), str(manifest))
    report.write_bytes(report_bytes + b" ")

    with pytest.raises(filesystem.VirusScanError, match="content changed"):
        filesystem.verify_approved_scan_report(str(report), report_sha256, str(target), str(manifest))

    report.write_bytes(report_bytes)
    infected.write_bytes(b"changed after approval")

    with pytest.raises(filesystem.VirusScanError, match="hashes differ"):
        filesystem.verify_approved_scan_report(str(report), report_sha256, str(target), str(manifest))
