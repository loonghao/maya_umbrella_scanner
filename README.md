# Maya Umbrella Scanner — Autodesk Maya Scene Malware Scanner

[English](README.md) | [简体中文](README.zh-CN.md)

`maya_umbrella_scanner` is a portable Windows x64 CLI and Agent Skill for batch scanning and approval-gated cleanup of known malware in Autodesk Maya `.ma` and `.mb` scene files.

> [!TIP]
> **Agent Skills are supported.** If your Codex, WorkBuddy, or another client version supports Agent Skills, install `maya-umbrella-batch-antivirus` and request a Maya virus scan in natural language. The Skill coordinates scope confirmation, batch scanning, findings disclosure, explicit cleanup approval, backup verification, and an independent post-clean scan. This can reduce manual sequencing while preserving the safety gates.

## What is Maya Umbrella Scanner?

Maya Umbrella Scanner is a batch Maya virus scanner and controlled Maya antivirus workflow for Windows x64. It recursively checks exact directories for known signatures in Maya scene files. Scan mode does not launch Maya or rewrite scenes. Cleanup runs only after the findings are disclosed and approved, then uses the selected local Maya installation's `mayapy.exe` and Maya API to repair affected scenes.

The PyOxidizer release bundle embeds its Python runtime, so scanning does not require system Python. Cleanup still requires the exact Autodesk Maya year selected for the operation.

> [!IMPORTANT]
> This project handles Maya `.ma` and `.mb` scene malware. It is not a general system antivirus, and a clean scene report does not prove that Maya startup directories, the Maya installation, referenced files, or the rest of Windows are clean.

## Project components

| Name | Role |
| --- | --- |
| Maya Umbrella Scanner / `maya_umbrella_scanner` | Product and repository name |
| `maya_umbrella.exe` | Portable Windows x64 batch CLI |
| `maya-umbrella-scanner` | Agent Plugin name declared by [`plugin.json`](plugin.json) |
| `maya-umbrella-batch-antivirus` | Installable [Agent Skill](skills/maya-umbrella-batch-antivirus/SKILL.md) |

## Key capabilities

- Scan multiple explicitly selected directories in one run by repeating `--path`.
- Recursively inspect Maya `.ma` and `.mb` files without starting Maya in scan mode.
- Bind cleanup authorization to the same executable, target set, report bytes, infected paths, and source SHA-256 values.
- Create verified, no-clobber backups in adjacent `_virus` directories before any scene rewrite.
- Isolate Maya cleanup from existing startup hooks and finish with full-scope plus independent post-clean scans.
- Let Agent Skills-compatible clients, including supported Codex or WorkBuddy versions, orchestrate the workflow through a bounded Agent Skill.

## Requirements

| Task | Requirements |
| --- | --- |
| Scan | Windows x64 release bundle. No system Python or Autodesk Maya installation is required. |
| Cleanup | The same release bundle plus a local Autodesk Maya installation for the explicitly selected year. |
| Skill installation with `npx` | Node.js and npm are required only for this installation method, not for the scanner runtime. |
| Skill-local CLI installer | Windows PowerShell 5.1 or later, `%LOCALAPPDATA%`, and the current non-administrator user. |

## Installation

### Install the Agent Skill

Use the Skills CLI to install the repository's Skill. This example targets a global Codex installation; omit `--global` for project-level installation:

```powershell
npx --yes skills@1.5.23 add loonghao/maya_umbrella_scanner `
  --skill maya-umbrella-batch-antivirus `
  --agent codex `
  --global `
  --yes
```

For an Agent Skills-compatible WorkBuddy or another agent, import the same `maya-umbrella-batch-antivirus` Skill through that client's supported Skills entrypoint. The command above is specifically a Codex example.

If a compatible CLI is not installed, the Skill first shows the exact repository, release version, ZIP asset, checksum asset, and destination. After you approve that download, it runs its verified installer with the exact version:

```powershell
& "<skill-directory>\scripts\install_cli.ps1" -Version "<approved-version>"
```

The installer never selects `latest`, never overwrites an installed version, and returns the verified `maya_umbrella.exe` path as JSON. It installs to `%LOCALAPPDATA%\maya_umbrella_scanner\versions\<version>`. Run it as the current user, not from an elevated administrator PowerShell.

### Install the portable CLI manually

Download the exact `maya_umbrella_scanner-<version>.zip` and `SHA256SUMS` from the same [GitHub Release](https://github.com/loonghao/maya_umbrella_scanner/releases). Verify the ZIP's SHA-256, then extract the complete archive.

Keep the relative layout of `maya_umbrella.exe`, `bin`, and `lib`. The archive is a portable CLI bundle, not a standalone PE that can be separated from its companion files.

## How to scan and clean Maya scene malware

### Use an Agent Skills-compatible client (Codex, WorkBuddy, or another agent)

After installing the Skill, submit a bounded natural-language request:

```text
Use the maya-umbrella-batch-antivirus Skill to scan C:\project\scenes for Maya scene malware.
Show me the findings and report first. Do not clean anything without my explicit approval.
```

Intent selects the Skill; it does not authorize cleanup. Even when the request says “clean,” “remove,” or “antivirus,” the Skill scans first, discloses the exact findings and side effects, and waits for explicit approval.

### Verify the CLI contract

Require the batch commands and approval arguments introduced with the v0.2.0 batch contract. Probe capabilities instead of trusting a version string alone:

```powershell
.\maya_umbrella.exe --version
.\maya_umbrella.exe scan --help
.\maya_umbrella.exe clean --help
```

The executable must expose `scan`, `clean`, `--approved-scan-report`, and `--approved-scan-report-sha256`. The Skill must reject releases without that contract, including v0.1.8 and earlier, and must never fall back to the legacy single-root interface.

### Scan Maya scenes

Repeat `--path` to scan multiple exact directories. Every supplied `--report` must be a fresh, not-yet-existing `.json` path. A report is required when cleanup may follow:

```powershell
.\maya_umbrella.exe scan `
  --path "C:\project\scenes" `
  --path "D:\shots\asset" `
  --report "C:\temp\maya-umbrella-scan.json"
```

The report records each infected path and source SHA-256. The stdout JSON contains `report_file_sha256`, which binds the exact report bytes. Before cleanup, disclose the resolved roots, scanner path and version, infected-file list, source hashes, report digest, selected Maya year, and cleanup side effects.

Scan mode does not start Maya or rewrite scenes, although it may create temporary output and the requested report. A scan can cover an unusually broad root only after that exact scope is confirmed.

### Clean only after explicit approval

After the user approves the disclosed findings and effects, use the same executable, the same paths, the unchanged approved report and digest, and one explicitly selected Maya year:

```powershell
.\maya_umbrella.exe clean `
  --path "C:\project\scenes" `
  --path "D:\shots\asset" `
  --maya-version 2024 `
  --approved-scan-report "C:\temp\maya-umbrella-scan.json" `
  --approved-scan-report-sha256 "<approved-report-sha256>" `
  --confirm-clean `
  --report "C:\temp\maya-umbrella-clean.json"
```

`--confirm-clean` is a CLI guard, not a substitute for informed approval of the exact scope and side effects. The cleanup target can never be a drive root or the user's home directory, even if requested. Cleanup also rejects symlinks, junctions, and reparse points.

Cleanup force-saves repaired scenes in place after staging and verifying adjacent `_virus` backups. It stops on drift, backup collision, identity alias, hash mismatch, insufficient evidence, or an indeterminate target.

Ensure no interactive Maya session is editing the target scenes during cleanup. After cleanup, run one additional independent scan with the same executable and paths and a third fresh report:

```powershell
.\maya_umbrella.exe scan `
  --path "C:\project\scenes" `
  --path "D:\shots\asset" `
  --report "C:\temp\maya-umbrella-post-clean-scan.json"
```

Call the active scene scope clean only when cleanup completed without an indeterminate target, expected backups exist, the CLI's full-scope final scan succeeded, and the independent post-clean scan reports no remaining signatures.

## Safety contract

The authoritative workflow is defined in the [Agent Skill](skills/maya-umbrella-batch-antivirus/SKILL.md) and its [operation contract](skills/maya-umbrella-batch-antivirus/references/operation-contract.md). The essential guarantees are:

- Approval binds the scanner path, target set, report bytes, infected paths, and source hashes. The Maya year is an additional explicit cleanup parameter and approval item.
- `_virus` is the fixed backup/quarantine directory. Do not set `MAYA_UMBRELLA_IGNORE_BACKUP=true` or customize `MAYA_UMBRELLA_BACKUP_FOLDER_NAME`.
- Signature scans exclude `_virus`, which may contain infected original scene bytes. Preserve and quarantine those backups accordingly; a clean result does not prove the backup directory is clean.
- Existing same-name backups are never overwritten. Preserve or relocate them only with approval, then scan again.
- Cleanup pre-creates an empty `Maya.env`, uses an isolated temporary `MAYA_APP_DIR`, and disables Python user-site.
- Existing `Maya.env`, `userSetup.py`, `userSetup.mel`, `.pth`, `sitecustomize.py`, module paths, plug-in paths, and custom script paths are not executed or deleted.
- Infected references or Maya/Python files outside the approved scene manifest abort cleanup before scene modification. They require a separate scope and approval.
- `indeterminate` is a failure state, never a clean result. A successful cleanup exit code alone is not sufficient verification.

## Compatibility and limitations

- The portable release targets Windows x64.
- Scan mode does not require Maya. Cleanup requires the exact locally installed Maya year selected for that run.
- Maya 2019–2021 use Python 2 and cannot safely save non-ASCII scene paths through the current engine. The CLI refuses that combination before backup or Maya startup.
- Do not move, rename, or copy scenes after approval to work around a path failure. Selecting another Maya year requires a fresh scan and approval.
- Saving through a newer Maya version can change scene compatibility.
- The scanner detects the known signatures supported by its pinned engine; it does not provide a general malware-analysis guarantee.

## Agent Plugin and Skill distribution

The repository follows [Agent Plugins 1.0](https://agent-plugins.org/specification). [`plugin.json`](plugin.json) is the package manifest, and compatible clients discover the standalone [`skills/maya-umbrella-batch-antivirus/SKILL.md`](skills/maya-umbrella-batch-antivirus/SKILL.md) entrypoint from the fixed `skills/` layout. The Agent Plugins specification defines packaging, not a required installation or publishing service.

### ClawHub

ClawHub distributes the Skill directory rather than a package containing only the root manifest. Maintainers can validate a prospective publication with a pinned dry run:

```powershell
npx --yes clawhub@0.23.3 skill publish .\skills\maya-umbrella-batch-antivirus `
  --owner loonghao `
  --categories security,operations `
  --topics maya,antivirus,malware,virus-scan,scene-cleanup `
  --dry-run `
  --json
```

Run `npx --yes clawhub@0.23.3 login` before an authorized publication. With a configured `CLAWHUB_TOKEN` secret, every non-prerelease GitHub Release triggers the `ClawHub Skill` workflow; `workflow_dispatch` is restricted to `main` for a controlled initial or recovery publication. The workflow pins ClawHub CLI 0.23.3 and preserves structured receipts. A `pending-publication` or `submitted` receipt means the registry workflow accepted or recorded the submission, but public availability has not yet been verified.

After a public version is confirmed visible, install it with:

```powershell
openclaw skills install @loonghao/maya-umbrella-batch-antivirus
# Or use the ClawHub registry CLI
npx --yes clawhub@0.23.3 install @loonghao/maya-umbrella-batch-antivirus
```

## Frequently asked questions

### Can an Agent Skills-compatible Codex or WorkBuddy scan and clean Maya scene malware?

Yes, when that client version supports Agent Skills and can access the Windows CLI. Install `maya-umbrella-batch-antivirus`, then ask it to scan an exact directory. Controlled cleanup still requires findings disclosure and explicit approval after the scan. The repository validates Skill discovery and the bounded workflow; it does not claim end-to-end validation for every Agent client version.

### Does scanning modify Maya files?

No. Scan mode does not launch Maya or rewrite scenes. It may write temporary output and a requested JSON report. Cleanup is a separate, approval-gated operation that force-saves repaired scenes after verified backups are staged.

### Does it require Python or Autodesk Maya?

The portable release embeds its Python runtime, so neither scanning nor cleanup requires system Python. Scanning does not require Maya. Cleanup requires the exact selected Autodesk Maya year because repair runs through that installation's `mayapy.exe` and Maya API.

### Does it clean `userSetup.py` or the entire Maya installation?

No. Read-only discovery can report matching external Maya/Python files, but this workflow does not delete them. A clean scene scan does not clear startup directories, the Maya installation, infected references, or other external files.

### Is Maya Umbrella Scanner a general antivirus?

No. It is a scoped Maya scene virus scanner for `.ma` and `.mb` files. Keep endpoint protection and broader Maya security controls in place.

## Release and architecture

Release Please owns versions and the changelog. It synchronizes `pyproject.toml`, `maya_umbrella_scanner/__version__.py`, `plugin.json`, and the release manifest, then creates a `vX.Y.Z` tag and GitHub Release. The tag workflow uses pinned build tools to produce the Windows portable ZIP and `SHA256SUMS`.

Reruns never overwrite existing release assets. If an earlier run uploaded only the ZIP, a rerun can add the checksum for those exact bytes; a mismatch between an existing ZIP and checksum fails closed.

See [ADR 0001](docs/adr/0001-portable-cli-runtime.md) for the runtime architecture and the decision not to perform an immediate full Rust rewrite.

## License

Maya Umbrella Scanner is released under the [MIT License](LICENSE).
