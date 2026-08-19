"""Behavior and packaging tests for the portable Agent Skill."""

# Import built-in modules
import json
from pathlib import Path
import re
import shutil

# Import third-party modules
import pytest

# Import local modules
from maya_umbrella_scanner import batch_cli as batch_scan
from maya_umbrella_scanner.__version__ import __version__


REPOSITORY_ROOT = Path(__file__).parents[1]
SKILL_ROOT = REPOSITORY_ROOT / "skills" / "maya-umbrella-batch-antivirus"
INSTALL_SCRIPT = SKILL_ROOT / "scripts" / "install_cli.ps1"


def scanner_result_for(files, manifest):
    if not files:
        return batch_scan.ProcessResult(0, f"{batch_scan.NO_INFECTION_MARKER}\n", "")
    manifest.write_text("\n".join(str(path) for path in files) + "\n", encoding="utf-8")
    return batch_scan.ProcessResult(0, f"{batch_scan.MANIFEST_MARKER} {manifest}\n", "")


def test_agent_plugin_and_skill_identity_match_layout():
    plugin = json.loads((REPOSITORY_ROOT / "plugin.json").read_text(encoding="utf-8"))
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert plugin["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert plugin["name"] == "maya-umbrella-scanner"
    assert set(plugin) <= {
        "$schema",
        "name",
        "version",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "extensions",
    }
    assert skill_text.startswith("---\nname: maya-umbrella-batch-antivirus\n")
    assert INSTALL_SCRIPT.is_file()


def test_skill_description_exposes_maya_antivirus_intent_in_both_languages():
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"^description: (?P<description>.+)$", skill_text, re.MULTILINE)

    assert match
    description = match.group("description")
    assert len(description) <= 220
    assert all(
        phrase in description
        for phrase in (
            "Maya杀毒",
            "Maya病毒扫描",
            "Maya病毒查杀",
            "清理Maya病毒",
            "病毒查杀",
            "Maya antivirus",
        )
    )
    assert "not general antivirus" in description
    assert all(phrase not in description for phrase in ("恶意脚本检测", "场景清理"))
    assert "metadata:\n  openclaw:\n    os: [win32]" in skill_text


def test_clawhub_release_workflow_uses_pinned_cli_and_catalog_metadata():
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "clawhub-skill.yml").read_text(
        encoding="utf-8"
    )

    assert "  release:\n    types: [published]" in workflow
    assert "github.event_name != 'release' || github.event.release.prerelease == false" in workflow
    assert "github.event_name == 'pull_request' && github.ref || 'publish'" in workflow
    assert 'CLAWHUB_CLI_VERSION: "0.23.3"' in workflow
    assert "npm install --global --ignore-scripts --no-audit --no-fund" in workflow
    assert '"$(clawhub --cli-version)" == "$CLAWHUB_CLI_VERSION"' in workflow
    assert '"$(git rev-parse HEAD)" == "$GITHUB_SHA"' in workflow
    assert '"$(git status --short)"' in workflow
    assert "npx --yes" not in workflow
    assert "--categories security,operations" in workflow
    assert "--topics maya,antivirus,malware,virus-scan,scene-cleanup" in workflow
    assert 'receipt.status === "unchanged" && receipt.version === receipt.latestVersion' in workflow
    assert 'receipt.status === "would-publish" && receipt.latestVersion === null' in workflow
    assert "publish_version=" in workflow
    assert '--version "$publish_version"' in workflow
    assert "secrets.CLAWHUB_TOKEN" in workflow
    assert '"$GITHUB_REF" != "refs/heads/main"' in workflow
    assert "validate_clawhub_publish.py" in workflow
    assert 'rm -f -- "$CLAWHUB_CONFIG_PATH"' in workflow
    assert "clawhub-*.json" not in workflow
    assert "openclaw/clawhub/.github/workflows/skill-publish.yml" not in workflow

    install_index = workflow.index("- name: Install pinned ClawHub CLI")
    write_config_index = workflow.index("- name: Write ephemeral ClawHub configuration")
    publish_index = workflow.index("- name: Preview and optionally publish the Skill")
    assert install_index < write_config_index < publish_index

    write_config_step = workflow.partition("- name: Write ephemeral ClawHub configuration")[
        2
    ].partition("\n      - name:")[0]
    assert "CLAWHUB_CONFIG_PATH: ${{ runner.temp }}/clawhub-config.json" in write_config_step
    assert "CLAWHUB_TOKEN: ${{ secrets.CLAWHUB_TOKEN }}" in write_config_step
    assert "process.env.CLAWHUB_CONFIG_PATH" in write_config_step


def test_portable_build_pins_the_tested_scanner_engine():
    build_config = (REPOSITORY_ROOT / "pyoxidizer.bzl").read_text(encoding="utf-8")
    project_config = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    release_actions = (REPOSITORY_ROOT / "nox_actions" / "release.py").read_text(encoding="utf-8")
    release_workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "python-publish.yml").read_text(
        encoding="utf-8"
    )

    assert 'maya-umbrella = "0.18.0"' in project_config
    assert 'click = "8.1.7"' in project_config
    assert '"maya-umbrella==0.18.0"' in build_config
    assert '"click==8.1.7"' in build_config
    assert '"colorama==0.4.6"' in build_config
    assert 'exe.pip_install(["--no-deps", "."])' in build_config
    assert 'session.install("pyoxidizer==0.24.0")' in release_actions
    assert 'requires = ["poetry-core==2.2.1"]' in project_config
    assert "python -m pip install poetry==2.2.1 nox==2026.2.9" in release_workflow
    assert "requirements-dev.txt" not in release_workflow


def test_release_please_owns_and_synchronizes_product_versions():
    project_config = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    module_version_source = (REPOSITORY_ROOT / "maya_umbrella_scanner" / "__version__.py").read_text(
        encoding="utf-8"
    )
    plugin = json.loads((REPOSITORY_ROOT / "plugin.json").read_text(encoding="utf-8"))
    manifest = json.loads((REPOSITORY_ROOT / ".release-please-manifest.json").read_text(encoding="utf-8"))
    release_config = json.loads((REPOSITORY_ROOT / "release-please-config.json").read_text(encoding="utf-8"))
    release_workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "release-please.yml").read_text(
        encoding="utf-8"
    )
    publish_workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "python-publish.yml").read_text(
        encoding="utf-8"
    )
    poetry_section = project_config.split("[tool.poetry]", 1)[1].split("[", 1)[0]
    project_version = re.search(r'^version = "([^"]+)"$', poetry_section, re.MULTILINE)

    assert project_version
    assert project_version.group(1) == plugin["version"] == manifest["."] == __version__
    assert "# x-release-please-version" in module_version_source
    assert "tool.commitizen" not in project_config
    assert not (REPOSITORY_ROOT / ".github" / "workflows" / "bumpversion.yml").exists()
    assert release_config["packages"]["."]["release-type"] == "python"
    assert {entry["path"] for entry in release_config["packages"]["."]["extra-files"]} == {
        "maya_umbrella_scanner/__version__.py",
        "plugin.json",
    }
    assert "googleapis/release-please-action@45996ed1f6d02564a971a2fa1b5860e934307cf7" in release_workflow
    assert "secrets.PERSONAL_ACCESS_TOKEN" in release_workflow
    assert "ncipollo/release-action" not in publish_workflow
    assert "gh release upload" in publish_workflow
    assert "Existing release ZIP and SHA256SUMS disagree" in publish_workflow
    assert "bind the checksum to those" in publish_workflow
    assert 'state -eq "starter"' in publish_workflow
    assert 'state -ne "uploaded"' in publish_workflow
    assert "--method DELETE" in publish_workflow
    assert publish_workflow.index('state -eq "starter"') < publish_workflow.index("$archiveAssets = @(")
    assert "--clobber" not in publish_workflow


def test_scan_reports_infection_without_running_maya(tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_text("signature", encoding="utf-8")
    manifest = tmp_path / "infected.txt"
    calls = []

    def runner(scanner, current_target, maya_version, env, approved_scan_report, approved_report_sha256):
        calls.append((maya_version, approved_scan_report))
        return scanner_result_for([infected], manifest)

    report = batch_scan.execute_batch("scan", "scanner.exe", [target], runner=runner)

    assert report["completed"] is True
    assert report["infection_free"] is False
    assert report["targets"][0]["status"] == "infected"
    assert report["targets"][0]["infected_sha256_before"][str(infected)] == batch_scan.sha256_file(infected)
    assert calls == [(None, None)]


def test_cleanup_requires_confirmation(tmp_path):
    with pytest.raises(batch_scan.BatchScanError, match="confirm-clean"):
        batch_scan.execute_batch("clean", "scanner.exe", [tmp_path], maya_version="2024")


def test_cleanup_requires_approved_scan_report(tmp_path):
    with pytest.raises(batch_scan.BatchScanError, match="approved-scan-report"):
        batch_scan.execute_batch("clean", "scanner.exe", [tmp_path], maya_version="2024", confirmed=True)


def test_python2_maya_rejects_non_ascii_scene_before_backup(tmp_path):
    target = tmp_path / "中文场景"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"infected scene")
    manifest = tmp_path / "infected.txt"
    calls = []

    def runner(scanner, current_target, maya_version, env, approved_scan_report, approved_report_sha256):
        calls.append(maya_version)
        if maya_version:
            pytest.fail("Maya must not start for an unsupported Python 2 path")
        return scanner_result_for([infected], manifest)

    report = batch_scan.execute_batch(
        "clean",
        "scanner.exe",
        [target],
        maya_version="2020",
        confirmed=True,
        approved_findings={str(target): {str(infected): batch_scan.sha256_file(infected)}},
        approved_scan_report=str(tmp_path / "approved.json"),
        approved_report_sha256="a" * 64,
        runner=runner,
    )

    assert report["completed"] is False
    assert "cannot safely open non-ASCII" in report["targets"][0]["error"]
    assert calls == [None]
    assert not (target / "_virus").exists()


def test_cleanup_verifies_backup_hash_and_post_scan(tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"infected scene")
    manifest = tmp_path / "infected.txt"
    scan_count = 0
    environments = []
    approvals = []

    def runner(scanner, current_target, maya_version, env, approved_scan_report, approved_report_sha256):
        nonlocal scan_count
        environments.append(dict(env))
        approvals.append((approved_scan_report, approved_report_sha256))
        if maya_version:
            backup = infected.parent / "_virus" / infected.name
            backup.parent.mkdir(exist_ok=True)
            shutil.copy2(infected, backup)
            infected.write_bytes(b"clean scene")
            return batch_scan.ProcessResult(0, "cleaned", "")
        scan_count += 1
        return scanner_result_for([infected], manifest) if scan_count == 1 else scanner_result_for([], manifest)

    report = batch_scan.execute_batch(
        "clean",
        "scanner.exe",
        [target],
        maya_version="2024",
        confirmed=True,
        approved_findings={str(target): {str(infected): batch_scan.sha256_file(infected)}},
        approved_scan_report=str(tmp_path / "approved.json"),
        approved_report_sha256="a" * 64,
        runner=runner,
    )

    item = report["targets"][0]
    assert report["completed"] is True
    assert report["infection_free"] is True
    assert item["status"] == "cleaned"
    assert item["backups"][0]["matches_source"] is True
    assert all(env["MAYA_UMBRELLA_IGNORE_BACKUP"] == "false" for env in environments)
    assert approvals == [
        (None, None),
        (str(tmp_path / "approved.json"), "a" * 64),
        (None, None),
    ]


def test_existing_backup_blocks_cleanup_before_mutation(tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"infected scene")
    backup = target / "_virus" / infected.name
    backup.parent.mkdir()
    backup.write_bytes(b"older backup")
    manifest = tmp_path / "infected.txt"
    calls = []

    def runner(scanner, current_target, maya_version, env, approved_scan_report, approved_report_sha256):
        calls.append((maya_version, approved_scan_report))
        return scanner_result_for([infected], manifest)

    report = batch_scan.execute_batch(
        "clean",
        "scanner.exe",
        [target],
        maya_version="2024",
        confirmed=True,
        approved_findings={str(target): {str(infected): batch_scan.sha256_file(infected)}},
        approved_scan_report=str(tmp_path / "approved.json"),
        approved_report_sha256="a" * 64,
        runner=runner,
    )

    assert report["completed"] is False
    assert report["targets"][0]["status"] == "error"
    assert "would be overwritten" in report["targets"][0]["error"]
    assert calls == [(None, None)]
    assert infected.read_bytes() == b"infected scene"


def test_backup_copy_failure_blocks_maya_before_mutation(monkeypatch, tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"infected scene")
    manifest = tmp_path / "infected.txt"
    calls = []

    def runner(scanner, current_target, maya_version, env, approved_scan_report, approved_report_sha256):
        calls.append(maya_version)
        return scanner_result_for([infected], manifest)

    monkeypatch.setattr(
        batch_scan,
        "_copy_backup_exclusive",
        lambda *args: (_ for _ in ()).throw(batch_scan.BatchScanError("denied")),
    )
    report = batch_scan.execute_batch(
        "clean",
        "scanner.exe",
        [target],
        maya_version="2024",
        confirmed=True,
        approved_findings={str(target): {str(infected): batch_scan.sha256_file(infected)}},
        approved_scan_report=str(tmp_path / "approved.json"),
        approved_report_sha256="a" * 64,
        runner=runner,
    )

    assert report["completed"] is False
    assert "denied" in report["targets"][0]["error"]
    assert calls == [None]
    assert infected.read_bytes() == b"infected scene"


def test_backup_reparse_directory_blocks_cleanup_before_copy(monkeypatch, tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    infected = target / "infected.ma"
    infected.write_bytes(b"infected scene")
    backup_directory = target / "_virus"
    backup_directory.mkdir()
    copied = False

    def copy_backup(*args):
        nonlocal copied
        copied = True

    monkeypatch.setattr(batch_scan, "_is_reparse_point", lambda path: path == backup_directory)
    monkeypatch.setattr(batch_scan, "_copy_backup_exclusive", copy_backup)

    with pytest.raises(batch_scan.BatchScanError, match="regular local directory"):
        batch_scan.preflight_backups([infected], "_virus")

    assert copied is False
    assert not (backup_directory / infected.name).exists()


def test_cleanup_target_reparse_component_is_rejected(monkeypatch, tmp_path):
    target = tmp_path / "approved"
    target.mkdir()
    monkeypatch.setattr(batch_scan, "_is_reparse_point", lambda path: path == target)

    with pytest.raises(batch_scan.BatchScanError, match="symlinks or junctions"):
        batch_scan.normalize_targets([str(target)], cleaning=True)


def test_approval_hash_drift_blocks_entire_cleanup_batch(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    first_infected = first / "infected.ma"
    second_infected = second / "infected.mb"
    first_infected.write_bytes(b"first")
    second_infected.write_bytes(b"second")
    manifests = {first: tmp_path / "first.txt", second: tmp_path / "second.txt"}
    calls = []

    def runner(scanner, current_target, maya_version, env, approved_scan_report, approved_report_sha256):
        calls.append((current_target, maya_version))
        infected = first_infected if current_target == first else second_infected
        return scanner_result_for([infected], manifests[current_target])

    report = batch_scan.execute_batch(
        "clean",
        "scanner.exe",
        [first, second],
        maya_version="2024",
        confirmed=True,
        approved_findings={
            str(first): {str(first_infected): "0" * 64},
            str(second): {str(second_infected): batch_scan.sha256_file(second_infected)},
        },
        approved_scan_report=str(tmp_path / "approved.json"),
        approved_report_sha256="a" * 64,
        runner=runner,
    )

    assert report["completed"] is False
    assert report["targets"][0]["status"] == "error"
    assert report["targets"][1]["status"] == "skipped"
    assert all(maya_version is None for _, maya_version in calls)
    assert first_infected.read_bytes() == b"first"
    assert second_infected.read_bytes() == b"second"


def test_final_verification_covers_initially_clean_targets(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    first_infected = first / "infected.ma"
    late_infected = second / "late.mb"
    first_infected.write_bytes(b"infected")
    manifests = {first: tmp_path / "first.txt", second: tmp_path / "second.txt"}
    scan_counts = {first: 0, second: 0}

    def runner(scanner, current_target, maya_version, env, approved_scan_report, approved_report_sha256):
        if maya_version:
            backup = first / "_virus" / first_infected.name
            backup.parent.mkdir(exist_ok=True)
            shutil.copy2(first_infected, backup)
            first_infected.write_bytes(b"clean")
            late_infected.write_bytes(b"arrived during another target cleanup")
            return batch_scan.ProcessResult(0, "cleaned", "")
        scan_counts[current_target] += 1
        if current_target == first:
            files = [first_infected] if scan_counts[current_target] == 1 else []
        else:
            files = [] if scan_counts[current_target] == 1 else [late_infected]
        return scanner_result_for(files, manifests[current_target])

    report = batch_scan.execute_batch(
        "clean",
        "scanner.exe",
        [first, second],
        maya_version="2024",
        confirmed=True,
        approved_findings={
            str(first): {str(first_infected): batch_scan.sha256_file(first_infected)},
            str(second): {},
        },
        approved_scan_report=str(tmp_path / "approved.json"),
        approved_report_sha256="a" * 64,
        runner=runner,
    )

    assert report["completed"] is False
    assert report["infection_free"] is False
    assert report["targets"][0]["status"] == "cleaned"
    assert report["targets"][1]["status"] == "error"
    assert report["targets"][1]["infected_after"] == [str(late_infected)]


def test_scanner_fault_is_indeterminate_not_clean(tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()

    def runner(scanner, current_target, maya_version, env, approved_scan_report, approved_report_sha256):
        return batch_scan.ProcessResult(2, "", "access denied")

    report = batch_scan.execute_batch("scan", "scanner.exe", [target], runner=runner)

    assert report["completed"] is False
    assert report["infection_free"] is False
    assert report["targets"][0]["status"] == "error"


def test_backup_folder_name_rejects_glob_metacharacters():
    with pytest.raises(batch_scan.BatchScanError, match="reserved value _virus"):
        batch_scan.validate_backup_folder_name("*")


@pytest.mark.parametrize("name", ["NUL", "con.txt", "AUX", "foo.", "...", "a" * 256])
def test_backup_folder_name_rejects_unsafe_windows_components(name):
    with pytest.raises(batch_scan.BatchScanError, match="reserved value _virus"):
        batch_scan.validate_backup_folder_name(name)


def test_backup_folder_name_cannot_hide_existing_project_tree():
    with pytest.raises(batch_scan.BatchScanError, match="reserved value _virus"):
        batch_scan.validate_backup_folder_name("assets")


def test_legacy_ripgrep_no_match_is_accepted_but_other_failures_are_not(tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    clean = batch_scan.ProcessResult(
        0,
        "Command returned non-zero exit status 1.\nNo infected files found.\n",
        "",
    )
    failed = batch_scan.ProcessResult(
        0,
        "Command returned non-zero exit status 10.\nNo infected files found.\n",
        "",
    )

    assert batch_scan.interpret_scan(clean, target) == []
    with pytest.raises(batch_scan.BatchScanError, match="internal failure"):
        batch_scan.interpret_scan(failed, target)


def test_report_destination_must_be_fresh_json(tmp_path):
    existing = tmp_path / "report.json"
    existing.write_text("preserve me", encoding="utf-8")

    with pytest.raises(batch_scan.BatchScanError, match="already exists"):
        batch_scan.prepare_report_path(str(existing))
    with pytest.raises(batch_scan.BatchScanError, match=".json extension"):
        batch_scan.prepare_report_path(str(tmp_path / "scene.ma"))

    assert existing.read_text(encoding="utf-8") == "preserve me"


def test_report_write_preserves_preexisting_neighbor_tmp_file(tmp_path):
    report_path = tmp_path / "report.json"
    neighbor = tmp_path / "report.json.tmp"
    neighbor.write_text("unrelated", encoding="utf-8")

    batch_scan.write_report(report_path, {"completed": True})

    assert json.loads(report_path.read_text(encoding="utf-8")) == {"completed": True}
    assert neighbor.read_text(encoding="utf-8") == "unrelated"


def test_report_write_never_overwrites_raced_destination(tmp_path):
    report_path = tmp_path / "report.json"
    report_path.write_text("raced content", encoding="utf-8")

    with pytest.raises(FileExistsError):
        batch_scan.write_report(report_path, {"completed": True})

    assert report_path.read_text(encoding="utf-8") == "raced content"


def test_report_write_failure_preserves_full_operation_result(monkeypatch, tmp_path, capsys):
    target = tmp_path / "scenes"
    target.mkdir()
    report_path = tmp_path / "result.json"
    operation_report = {
        "schema_version": 1,
        "mode": "scan",
        "completed": True,
        "infection_free": True,
        "targets": [{"path": str(target), "status": "clean"}],
    }
    monkeypatch.setattr(batch_scan, "resolve_scanner", lambda value: "scanner.exe")
    monkeypatch.setattr(batch_scan, "execute_batch", lambda **kwargs: dict(operation_report))
    monkeypatch.setattr(batch_scan, "write_report", lambda *args: (_ for _ in ()).throw(OSError("disk full")))

    exit_code = batch_scan.main(["scan", "--path", str(target), "--report", str(report_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["targets"] == operation_report["targets"]
    assert output["completed"] is False
    assert output["infection_free"] is False
    assert "disk full" in output["report_write_error"]


def test_scan_prints_digest_for_exact_report_bytes(monkeypatch, tmp_path, capsys):
    target = tmp_path / "scenes"
    target.mkdir()
    report_path = tmp_path / "scan.json"
    operation_report = {
        "schema_version": 1,
        "mode": "scan",
        "completed": True,
        "infection_free": True,
        "targets": [{"path": str(target), "status": "clean"}],
    }
    monkeypatch.setattr(batch_scan, "resolve_scanner", lambda value: "scanner.exe")
    monkeypatch.setattr(batch_scan, "execute_batch", lambda **kwargs: dict(operation_report))

    exit_code = batch_scan.main(["scan", "--path", str(target), "--report", str(report_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["report_file_sha256"] == batch_scan.sha256_file(report_path)


def test_scan_digest_is_bound_before_published_file_can_change(monkeypatch, tmp_path, capsys):
    target = tmp_path / "scenes"
    target.mkdir()
    report_path = tmp_path / "scan.json"
    operation_report = {
        "schema_version": 1,
        "mode": "scan",
        "completed": True,
        "infection_free": True,
        "targets": [{"path": str(target), "status": "clean"}],
    }
    monkeypatch.setattr(batch_scan, "resolve_scanner", lambda value: "scanner.exe")
    monkeypatch.setattr(batch_scan, "execute_batch", lambda **kwargs: dict(operation_report))
    real_write_report = batch_scan.write_report

    def publish_then_tamper(path, report):
        digest = real_write_report(path, report)
        path.write_text("tampered after publish", encoding="utf-8")
        return digest

    monkeypatch.setattr(batch_scan, "write_report", publish_then_tamper)

    batch_scan.main(["scan", "--path", str(target), "--report", str(report_path)])
    output = json.loads(capsys.readouterr().out)
    expected_payload = (json.dumps(operation_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    assert output["report_file_sha256"] == batch_scan.hashlib.sha256(expected_payload).hexdigest()
    assert output["report_file_sha256"] != batch_scan.sha256_file(report_path)


def test_report_preflight_requires_hard_link_support(monkeypatch, tmp_path):
    monkeypatch.setattr(batch_scan.os, "link", lambda *args: (_ for _ in ()).throw(OSError("unsupported")))

    with pytest.raises(batch_scan.BatchScanError, match="atomically publish"):
        batch_scan.prepare_report_path(str(tmp_path / "report.json"))


def test_approved_report_must_match_user_accepted_digest(tmp_path):
    target = tmp_path / "scenes"
    target.mkdir()
    report_path = tmp_path / "scan.json"
    report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "scan",
                "scanner": "scanner.exe",
                "completed": True,
                "targets": [
                    {
                        "path": str(target),
                        "infected_before": [],
                        "infected_sha256_before": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    approved_digest = batch_scan.sha256_file(report_path)
    report_path.write_text(report_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(batch_scan.BatchScanError, match="accepted by the user"):
        batch_scan.load_approved_scan(
            str(report_path),
            approved_digest,
            "scanner.exe",
            [target],
        )
