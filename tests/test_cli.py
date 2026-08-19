"""Tests for cleanup failure propagation and verification."""

# Import built-in modules
import hashlib
import json
import os
import sys
import types

# Import third-party modules
import click
import pytest

# Import local modules
from maya_umbrella_scanner import cli


def test_cleanup_propagates_maya_failure(monkeypatch, tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "maya_umbrella",
            "--path",
            str(target),
            "--maya-version",
            "2024",
            "--approved-scan-report",
            str(tmp_path / "approved.json"),
            "--approved-scan-report-sha256",
            "a" * 64,
        ],
    )
    monkeypatch.setattr(cli, "assemble_rg_varius_check_commands", lambda path: "infected.txt")
    monkeypatch.setattr(cli, "verify_approved_scan_report", lambda *args: None)
    monkeypatch.setattr(cli, "resolve_maya_python", lambda version: str(tmp_path / "Maya2024/bin/mayapy.exe"))
    monkeypatch.setattr(cli, "run_maya_cleanup", lambda *args: 7)

    with pytest.raises(click.ClickException, match="exit code 7"):
        cli.main()


def test_cleanup_is_followed_by_a_fresh_scan(monkeypatch, tmp_path, capsys):
    target = tmp_path / "scenes"
    target.mkdir()
    scan_results = iter(("infected.txt", None))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "maya_umbrella",
            "--path",
            str(target),
            "--maya-version",
            "2024",
            "--approved-scan-report",
            str(tmp_path / "approved.json"),
            "--approved-scan-report-sha256",
            "a" * 64,
        ],
    )
    monkeypatch.setattr(cli, "assemble_rg_varius_check_commands", lambda path: next(scan_results))
    monkeypatch.setattr(cli, "verify_approved_scan_report", lambda *args: None)
    monkeypatch.setattr(cli, "resolve_maya_python", lambda version: str(tmp_path / "Maya2024/bin/mayapy.exe"))
    monkeypatch.setattr(cli, "run_maya_cleanup", lambda *args: 0)

    cli.main()

    assert "verification found no remaining signatures" in capsys.readouterr().out


def test_cleanup_refuses_disabled_backups(monkeypatch, tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    monkeypatch.setattr(sys, "argv", ["maya_umbrella", "--path", str(target), "--maya-version", "2024"])
    monkeypatch.setattr(cli, "assemble_rg_varius_check_commands", lambda path: "infected.txt")
    monkeypatch.setenv("MAYA_UMBRELLA_IGNORE_BACKUP", "true")

    with pytest.raises(click.ClickException, match="Refusing to clean"):
        cli.main()


def test_cleanup_approval_drift_blocks_maya_before_mutation(monkeypatch, tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "maya_umbrella",
            "--path",
            str(target),
            "--maya-version",
            "2024",
            "--approved-scan-report",
            str(tmp_path / "approved.json"),
            "--approved-scan-report-sha256",
            "a" * 64,
        ],
    )
    monkeypatch.setattr(cli, "assemble_rg_varius_check_commands", lambda path: "infected.txt")
    monkeypatch.setattr(
        cli,
        "verify_approved_scan_report",
        lambda *args: (_ for _ in ()).throw(cli.VirusScanError("drift")),
    )
    started = False

    def run_cleanup(*args):
        nonlocal started
        started = True
        return 0

    monkeypatch.setattr(cli, "run_maya_cleanup", run_cleanup)

    with pytest.raises(click.ClickException, match="approval verification failed.*drift"):
        cli.main()

    assert started is False


def test_maya_location_cannot_override_requested_year(monkeypatch, tmp_path):
    registered_root = tmp_path / "Maya2024"
    configured_root = tmp_path / "Maya2025"
    registered_mayapy = registered_root / "bin" / "mayapy.exe"
    configured_mayapy = configured_root / "bin" / "mayapy.exe"
    registered_mayapy.parent.mkdir(parents=True)
    configured_mayapy.parent.mkdir(parents=True)
    registered_mayapy.touch()
    configured_mayapy.touch()
    monkeypatch.setenv("MAYA_LOCATION", str(configured_root))

    def registered_lookup(version):
        assert "MAYA_LOCATION" not in cli.os.environ
        return str(registered_root)

    monkeypatch.setattr(cli, "get_maya_install_root", registered_lookup)
    monkeypatch.setattr(cli, "_query_maya_year", lambda path: "2024" if path == str(registered_mayapy) else "2025")

    resolved = cli.resolve_maya_python("2024")

    assert resolved == str(registered_mayapy)
    assert cli.os.environ["MAYA_LOCATION"] == str(configured_root)


def test_maya_location_fallback_must_report_requested_year(monkeypatch, tmp_path):
    configured_root = tmp_path / "Maya2025"
    configured_mayapy = configured_root / "bin" / "mayapy.exe"
    configured_mayapy.parent.mkdir(parents=True)
    configured_mayapy.touch()
    monkeypatch.setenv("MAYA_LOCATION", str(configured_root))
    monkeypatch.setattr(cli, "get_maya_install_root", lambda version: None)
    monkeypatch.setattr(cli, "_query_maya_year", lambda path: "2025")

    with pytest.raises(click.ClickException, match="reports Maya 2025, not requested Maya 2024"):
        cli.resolve_maya_python("2024")


def test_maya_year_query_uses_only_sentinel_line(monkeypatch, tmp_path):
    maya_python = tmp_path / "Maya2024" / "bin" / "mayapy.exe"
    maya_python.parent.mkdir(parents=True)
    maya_python.touch()
    completed = cli.subprocess.CompletedProcess(
        [],
        0,
        stdout="plugin log 2025\nMAYA_UMBRELLA_VERSION=2024.2\nshutdown log 2026\n",
        stderr="",
    )
    captured = {}

    def run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return completed

    monkeypatch.setattr(cli.subprocess, "run", run)

    assert cli._query_maya_year(str(maya_python)) == "2024"
    assert captured["command"][1:3] == ["-s", "-c"]
    assert captured["env"]["PYTHONNOUSERSITE"] == "1"


def test_runner_template_propagates_cleanup_error_after_uninitialize(monkeypatch, tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"infected")
    manifest = tmp_path / "infected.txt"
    manifest.write_text(f"{infected}\n", encoding="utf-8")
    report = tmp_path / "approved.json"
    report.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "path": str(target),
                        "infected_sha256_before": {
                            str(infected): hashlib.sha256(infected.read_bytes()).hexdigest()
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report_sha256 = hashlib.sha256(report.read_bytes()).hexdigest()
    backup = target / "_virus" / infected.name
    uninitialized = False

    class Defender:
        def __init__(self, auto_fix=False):
            self.collector = types.SimpleNamespace(
                infected_reference_files=[],
                malicious_files=[],
                infected_files=[],
                infected_nodes=["infectedNode"],
                infected_script_jobs=[],
            )
            self.virus_cleaner = types.SimpleNamespace(
                fix_infected_nodes=self.fail_scene_cleanup,
                fix_script_jobs=lambda: None,
            )

        def collect(self):
            return None

        def fail_scene_cleanup(self):
            raise RuntimeError("failed to fix infected-ref.ma")

    def uninitialize():
        nonlocal uninitialized
        uninitialized = True

    umbrella = types.ModuleType("maya_umbrella")
    maya_funs = types.ModuleType("maya_umbrella.maya_funs")
    maya_funs.open_maya_file = lambda path: None
    defender_module = types.ModuleType("maya_umbrella.defender")
    maya_funs.cmds = types.SimpleNamespace(file=lambda **kwargs: None)
    maya_funs.maya_standalone = types.SimpleNamespace(initialize=lambda: None, uninitialize=uninitialize)
    umbrella.maya_funs = maya_funs
    defender_module.MayaVirusDefender = Defender
    monkeypatch.setitem(sys.modules, "maya_umbrella", umbrella)
    monkeypatch.setitem(sys.modules, "maya_umbrella.maya_funs", maya_funs)
    monkeypatch.setitem(sys.modules, "maya_umbrella.defender", defender_module)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_maya.py", str(manifest), str(report), report_sha256, str(target)],
    )

    with pytest.raises(RuntimeError, match="infected-ref.ma"):
        exec(compile(cli.RUNNER_TEMPLATE, "run_maya.py", "exec"), {"__name__": "__main__"})  # noqa: S102

    assert backup.read_bytes() == b"infected"
    assert uninitialized is True


@pytest.mark.parametrize(
    ("references", "external_files", "message"),
    [
        ([r"Z:\outside\infected-ref.ma"], [], "separate approved scan"),
        ([], [r"Z:\outside\maya_secure_system.py"], "separate explicit remediation scope"),
    ],
)
def test_runner_template_blocks_unapproved_maya_scope_before_cleanup(
    monkeypatch, tmp_path, references, external_files, message
):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"infected")
    manifest = tmp_path / "infected.txt"
    manifest.write_text(f"{infected}\n", encoding="utf-8")
    report = tmp_path / "approved.json"
    report.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "path": str(target),
                        "infected_sha256_before": {
                            str(infected): hashlib.sha256(infected.read_bytes()).hexdigest()
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report_sha256 = hashlib.sha256(report.read_bytes()).hexdigest()
    cleanup_started = False
    uninitialized = False

    def uninitialize():
        nonlocal uninitialized
        uninitialized = True

    class Defender:
        def __init__(self, auto_fix=False):
            self.collector = types.SimpleNamespace(
                infected_reference_files=references,
                malicious_files=external_files,
                infected_files=[],
            )
            self.have_issues = True

        def collect(self):
            return None

        def fix(self):
            nonlocal cleanup_started
            cleanup_started = True

    umbrella = types.ModuleType("maya_umbrella")
    maya_funs = types.ModuleType("maya_umbrella.maya_funs")
    maya_funs.open_maya_file = lambda path: None
    defender_module = types.ModuleType("maya_umbrella.defender")
    maya_funs.cmds = types.SimpleNamespace(file=lambda **kwargs: None)
    maya_funs.maya_standalone = types.SimpleNamespace(initialize=lambda: None, uninitialize=uninitialize)
    umbrella.maya_funs = maya_funs
    defender_module.MayaVirusDefender = Defender
    monkeypatch.setitem(sys.modules, "maya_umbrella", umbrella)
    monkeypatch.setitem(sys.modules, "maya_umbrella.maya_funs", maya_funs)
    monkeypatch.setitem(sys.modules, "maya_umbrella.defender", defender_module)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_maya.py", str(manifest), str(report), report_sha256, str(target)],
    )

    with pytest.raises(RuntimeError, match=message):
        exec(compile(cli.RUNNER_TEMPLATE, "run_maya.py", "exec"), {"__name__": "__main__"})  # noqa: S102

    assert cleanup_started is False
    assert uninitialized is True


def test_runner_template_rechecks_hash_immediately_before_maya(monkeypatch, tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"approved bytes")
    manifest = tmp_path / "infected.txt"
    manifest.write_text(f"{infected}\n", encoding="utf-8")
    report = tmp_path / "approved.json"
    report.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "path": str(target),
                        "infected_sha256_before": {
                            str(infected): hashlib.sha256(infected.read_bytes()).hexdigest()
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report_sha256 = hashlib.sha256(report.read_bytes()).hexdigest()
    infected.write_bytes(b"changed before mayapy")
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_maya.py", str(manifest), str(report), report_sha256, str(target)],
    )

    with pytest.raises(RuntimeError, match="hashes changed before Maya startup"):
        exec(compile(cli.RUNNER_TEMPLATE, "run_maya.py", "exec"), {"__name__": "__main__"})  # noqa: S102


def test_runner_rejects_backup_hardlink_to_source(tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"approved bytes")
    backup = target / "_virus" / infected.name
    backup.parent.mkdir()
    try:
        os.link(infected, backup)
    except OSError as exc:
        pytest.skip(f"hard links are unavailable on this filesystem: {exc}")
    namespace = {"__name__": "runner_contract_test"}
    exec(compile(cli.RUNNER_TEMPLATE, "run_maya.py", "exec"), namespace)  # noqa: S102

    with pytest.raises(RuntimeError, match="not independent"):
        namespace["ensure_approved_backup"](
            str(infected),
            hashlib.sha256(infected.read_bytes()).hexdigest(),
        )

    assert backup.read_bytes() == b"approved bytes"


def test_runner_rejects_target_reparse_swap_before_maya(tmp_path):
    target = tmp_path / "approved"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"approved bytes")
    manifest = tmp_path / "infected.txt"
    manifest.write_text(f"{infected}\n", encoding="utf-8")
    report = tmp_path / "approved.json"
    report.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "path": str(target),
                        "infected_sha256_before": {
                            str(infected): hashlib.sha256(infected.read_bytes()).hexdigest()
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    namespace = {"__name__": "runner_contract_test"}
    exec(compile(cli.RUNNER_TEMPLATE, "run_maya.py", "exec"), namespace)  # noqa: S102
    original_is_reparse = namespace["is_reparse_point"]
    namespace["is_reparse_point"] = lambda path: (
        os.path.normcase(str(path)) == os.path.normcase(str(target)) or original_is_reparse(path)
    )

    with pytest.raises(RuntimeError, match="symlink or junction"):
        namespace["verify_cleanup_contract"](
            str(manifest),
            str(report),
            hashlib.sha256(report.read_bytes()).hexdigest(),
            str(target),
        )


def test_runner_rechecks_reparse_paths_after_initial_approval(monkeypatch, tmp_path):
    target = tmp_path / "approved"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"approved bytes")
    manifest = tmp_path / "infected.txt"
    manifest.write_text(f"{infected}\n", encoding="utf-8")
    report = tmp_path / "approved.json"
    report.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "path": str(target),
                        "infected_sha256_before": {
                            str(infected): hashlib.sha256(infected.read_bytes()).hexdigest()
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    namespace = {"__name__": "runner_contract_test"}
    exec(compile(cli.RUNNER_TEMPLATE, "run_maya.py", "exec"), namespace)  # noqa: S102
    namespace["verify_cleanup_contract"](
        str(manifest),
        str(report),
        hashlib.sha256(report.read_bytes()).hexdigest(),
        str(target),
    )
    opened = False

    def open_scene(path):
        nonlocal opened
        opened = True

    umbrella = types.ModuleType("maya_umbrella")
    maya_funs = types.ModuleType("maya_umbrella.maya_funs")
    maya_funs.open_maya_file = open_scene
    defender_module = types.ModuleType("maya_umbrella.defender")
    defender_module.MayaVirusDefender = lambda auto_fix=False: None
    umbrella.maya_funs = maya_funs
    monkeypatch.setitem(sys.modules, "maya_umbrella", umbrella)
    monkeypatch.setitem(sys.modules, "maya_umbrella.maya_funs", maya_funs)
    monkeypatch.setitem(sys.modules, "maya_umbrella.defender", defender_module)
    original_is_reparse = namespace["is_reparse_point"]
    namespace["is_reparse_point"] = lambda path: (
        os.path.normcase(str(path)) == os.path.normcase(str(target)) or original_is_reparse(path)
    )

    with pytest.raises(RuntimeError, match="symlink or junction"):
        namespace["inspect_approved_scenes"](
            types.SimpleNamespace(file=lambda **kwargs: None),
            [str(infected)],
        )

    assert opened is False


def test_runner_scene_cleanup_never_rechecks_or_deletes_late_external_files(monkeypatch, tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"approved bytes")
    external = tmp_path / "outside" / "maya_secure_system.py"
    scene_fixed = False

    class Collector:
        def __init__(self):
            self.infected_reference_files = []
            self.infected_files = []
            self.infected_nodes = ["infectedNode"]
            self.infected_script_jobs = []

        @property
        def malicious_files(self):
            external.parent.mkdir(exist_ok=True)
            external.write_bytes(b"appeared after the approved scope check")
            return []

    class Cleaner:
        def fix_infected_nodes(self):
            nonlocal scene_fixed
            scene_fixed = True

        def fix_script_jobs(self):
            return None

    class Defender:
        def __init__(self, auto_fix=False):
            self.collector = Collector()
            self.virus_cleaner = Cleaner()

        def collect(self):
            return None

        def fix(self):
            external.unlink()

    namespace = {"__name__": "runner_contract_test"}
    exec(compile(cli.RUNNER_TEMPLATE, "run_maya.py", "exec"), namespace)  # noqa: S102
    umbrella = types.ModuleType("maya_umbrella")
    maya_funs = types.ModuleType("maya_umbrella.maya_funs")
    maya_funs.open_maya_file = lambda path: None
    defender_module = types.ModuleType("maya_umbrella.defender")
    defender_module.MayaVirusDefender = Defender
    umbrella.maya_funs = maya_funs
    monkeypatch.setitem(sys.modules, "maya_umbrella", umbrella)
    monkeypatch.setitem(sys.modules, "maya_umbrella.maya_funs", maya_funs)
    monkeypatch.setitem(sys.modules, "maya_umbrella.defender", defender_module)
    commands = types.SimpleNamespace(file=lambda **kwargs: None)
    approved_digest = hashlib.sha256(infected.read_bytes()).hexdigest()

    namespace["clean_approved_scenes"](
        commands,
        [str(infected)],
        {namespace["resolved_path"](str(infected)): approved_digest},
    )

    assert scene_fixed is True
    assert external.read_bytes() == b"appeared after the approved scope check"
    assert (target / "_virus" / infected.name).read_bytes() == b"approved bytes"


def test_runner_rechecks_scene_hash_after_in_memory_fix_before_save(monkeypatch, tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"approved bytes")
    saved = False

    class Collector:
        def __init__(self):
            self.infected_reference_files = []
            self.infected_files = []
            self.infected_nodes = ["infectedNode"]
            self.infected_script_jobs = []
            self.malicious_files = []

    class Cleaner:
        def fix_infected_nodes(self):
            infected.write_bytes(b"concurrent disk change")

        def fix_script_jobs(self):
            return None

    class Defender:
        def __init__(self, auto_fix=False):
            self.collector = Collector()
            self.virus_cleaner = Cleaner()

        def collect(self):
            return None

    def file_command(**kwargs):
        nonlocal saved
        if kwargs.get("save"):
            saved = True

    namespace = {"__name__": "runner_contract_test"}
    exec(compile(cli.RUNNER_TEMPLATE, "run_maya.py", "exec"), namespace)  # noqa: S102
    umbrella = types.ModuleType("maya_umbrella")
    maya_funs = types.ModuleType("maya_umbrella.maya_funs")
    maya_funs.open_maya_file = lambda path: None
    defender_module = types.ModuleType("maya_umbrella.defender")
    defender_module.MayaVirusDefender = Defender
    umbrella.maya_funs = maya_funs
    monkeypatch.setitem(sys.modules, "maya_umbrella", umbrella)
    monkeypatch.setitem(sys.modules, "maya_umbrella.maya_funs", maya_funs)
    monkeypatch.setitem(sys.modules, "maya_umbrella.defender", defender_module)
    approved_digest = hashlib.sha256(infected.read_bytes()).hexdigest()

    with pytest.raises(RuntimeError, match="hash changed before save"):
        namespace["clean_approved_scenes"](
            types.SimpleNamespace(file=file_command),
            [str(infected)],
            {namespace["resolved_path"](str(infected)): approved_digest},
        )

    assert saved is False
    assert (target / "_virus" / infected.name).read_bytes() == b"approved bytes"


def test_runner_rechecks_backup_after_in_memory_fix_before_save(monkeypatch, tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"approved bytes")
    backup = target / "_virus" / infected.name
    saved = False

    class Collector:
        def __init__(self):
            self.infected_reference_files = []
            self.infected_files = []
            self.infected_nodes = ["infectedNode"]
            self.infected_script_jobs = []
            self.malicious_files = []

    class Cleaner:
        def fix_infected_nodes(self):
            backup.unlink()

        def fix_script_jobs(self):
            return None

    class Defender:
        def __init__(self, auto_fix=False):
            self.collector = Collector()
            self.virus_cleaner = Cleaner()

        def collect(self):
            return None

    def file_command(**kwargs):
        nonlocal saved
        if kwargs.get("save"):
            saved = True

    namespace = {"__name__": "runner_contract_test"}
    exec(compile(cli.RUNNER_TEMPLATE, "run_maya.py", "exec"), namespace)  # noqa: S102
    umbrella = types.ModuleType("maya_umbrella")
    maya_funs = types.ModuleType("maya_umbrella.maya_funs")
    maya_funs.open_maya_file = lambda path: None
    defender_module = types.ModuleType("maya_umbrella.defender")
    defender_module.MayaVirusDefender = Defender
    umbrella.maya_funs = maya_funs
    monkeypatch.setitem(sys.modules, "maya_umbrella", umbrella)
    monkeypatch.setitem(sys.modules, "maya_umbrella.maya_funs", maya_funs)
    monkeypatch.setitem(sys.modules, "maya_umbrella.defender", defender_module)
    approved_digest = hashlib.sha256(infected.read_bytes()).hexdigest()

    with pytest.raises(RuntimeError, match="Approved path component no longer exists"):
        namespace["clean_approved_scenes"](
            types.SimpleNamespace(file=file_command),
            [str(infected)],
            {namespace["resolved_path"](str(infected)): approved_digest},
        )

    assert saved is False
    assert infected.read_bytes() == b"approved bytes"
    assert not backup.exists()


def test_runner_preserves_approved_backup_when_scene_drifts_after_discovery(monkeypatch, tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"approved bytes")
    approved_digest = hashlib.sha256(infected.read_bytes()).hexdigest()
    backup = target / "_virus" / infected.name
    backup.parent.mkdir()
    backup.write_bytes(b"approved bytes")
    manifest = tmp_path / "infected.txt"
    manifest.write_text(f"{infected}\n", encoding="utf-8")
    report = tmp_path / "approved.json"
    report.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "path": str(target),
                        "infected_sha256_before": {str(infected): approved_digest},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report_sha256 = hashlib.sha256(report.read_bytes()).hexdigest()
    collect_count = 0
    cleanup_started = False
    uninitialized = False

    class Defender:
        def __init__(self, auto_fix=False):
            self.collector = types.SimpleNamespace(
                infected_reference_files=[],
                malicious_files=[],
                infected_files=[],
            )
            self.have_issues = True

        def collect(self):
            nonlocal collect_count
            collect_count += 1
            if collect_count == 1:
                infected.write_bytes(b"drifted after discovery")

        def fix(self):
            nonlocal cleanup_started
            cleanup_started = True

    def uninitialize():
        nonlocal uninitialized
        uninitialized = True

    umbrella = types.ModuleType("maya_umbrella")
    maya_funs = types.ModuleType("maya_umbrella.maya_funs")
    maya_funs.open_maya_file = lambda path: None
    maya_funs.cmds = types.SimpleNamespace(file=lambda **kwargs: None)
    maya_funs.maya_standalone = types.SimpleNamespace(initialize=lambda: None, uninitialize=uninitialize)
    defender_module = types.ModuleType("maya_umbrella.defender")
    defender_module.MayaVirusDefender = Defender
    umbrella.maya_funs = maya_funs
    monkeypatch.setitem(sys.modules, "maya_umbrella", umbrella)
    monkeypatch.setitem(sys.modules, "maya_umbrella.maya_funs", maya_funs)
    monkeypatch.setitem(sys.modules, "maya_umbrella.defender", defender_module)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_maya.py", str(manifest), str(report), report_sha256, str(target)],
    )

    with pytest.raises(RuntimeError, match="hash changed before cleanup"):
        exec(compile(cli.RUNNER_TEMPLATE, "run_maya.py", "exec"), {"__name__": "__main__"})  # noqa: S102

    assert backup.read_bytes() == b"approved bytes"
    assert infected.read_bytes() == b"drifted after discovery"
    assert cleanup_started is False
    assert uninitialized is True


def test_runner_template_accepts_python2_unicode_json_paths():
    assert "string_types = (basestring,)" in cli.RUNNER_TEMPLATE
    assert "text_type = unicode" in cli.RUNNER_TEMPLATE
    assert "sys.getfilesystemencoding()" in cli.RUNNER_TEMPLATE
    assert "does not support non-ASCII scene paths safely" in cli.RUNNER_TEMPLATE
    assert "isinstance(item.get('path'), string_types)" in cli.RUNNER_TEMPLATE
    assert "decode('utf-8-sig', 'replace')" in cli.RUNNER_TEMPLATE
    assert "maya_paths = [to_maya_path(path) for path in approved_paths]" in cli.RUNNER_TEMPLATE
    assert "MayaVirusDefender(auto_fix=False)" in cli.RUNNER_TEMPLATE
    assert "MayaVirusScanner" not in cli.RUNNER_TEMPLATE
    assert "defender.fix()" not in cli.RUNNER_TEMPLATE
    assert "os.path.realpath" not in cli.RUNNER_TEMPLATE
    assert "GetFileAttributesW" in cli.RUNNER_TEMPLATE
    assert "get_backup_path" not in cli.RUNNER_TEMPLATE
    assert "print(infected_file)" not in cli.RUNNER_TEMPLATE
