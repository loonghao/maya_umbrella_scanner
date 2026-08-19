---
name: maya-umbrella-batch-antivirus
description: Scan/clean Maya scene malware on Windows. Use for Maya杀毒, Maya病毒扫描, Maya病毒查杀, 清理Maya病毒, 病毒查杀, Maya antivirus, Maya virus scan/removal; not general antivirus.
metadata:
  openclaw:
    os: [win32]
---

# Maya Umbrella batch antivirus

Use this skill only on Windows with the portable `maya_umbrella.exe` CLI and Autodesk Maya scene files. The release bundle embeds its runtime, so do not require or install system Python. Cleanup still requires a locally installed Autodesk Maya version because scene repair runs inside that exact Maya's `mayapy.exe`.

## Interpret requests

- Treat `Maya杀毒`, `Maya病毒扫描`, `Maya病毒查杀`, `清理Maya病毒`, `Maya antivirus`, `Maya virus scan`, and requests to remove malware from `.ma` or `.mb` scenes as this skill's intent.
- If the request only says `病毒查杀`, `病毒扫描`, `杀毒`, `virus scan`, `virus removal`, or `antivirus` without Maya, `.ma`, `.mb`, or scene context, ask whether the target is Autodesk Maya scene files. Do not scan, download, or clean anything until that scope is confirmed.
- Keywords select this skill; they do not authorize cleanup. Treat scan, check, or detect wording as scan-only. For clean, remove, fix, remediate, `杀毒`, or `清理`, scan first and follow the existing findings disclosure and explicit cleanup approval contract.

Before use, run `maya_umbrella.exe --version`, `maya_umbrella.exe scan --help`, and `maya_umbrella.exe clean --help`. Require the batch subcommands plus `--approved-scan-report` and `--approved-scan-report-sha256`. If any capability is absent, stop and install a release containing this contract; do not bypass it with the legacy single-root interface.

Read [the operation contract](references/operation-contract.md) before running a scan, interpreting a report, or proposing cleanup. It documents the CLI arguments, backup behavior, and effects outside the requested scene roots.

## Establish the scope

- Resolve each requested `--path` to an absolute existing directory. Pass multiple targets by repeating `--path`; never broaden them with a shell glob or parent-directory substitution.
- Treat a drive root, user profile, shared production root, or other unusually broad target as unconfirmed until the user explicitly accepts that exact scope.
- Resolve one exact `maya_umbrella.exe` and keep its path and reported version in the evidence. Never download, replace, or switch builds without permission.
- Keep each cleanup run on one explicitly selected Maya version. The scanner queries the selected `mayapy.exe` and refuses a different year, even when `MAYA_LOCATION` points elsewhere. Ensure no interactive Maya session is concurrently editing the target scenes.
- Maya 2019-2021 use Python 2 and cannot safely save a non-ASCII scene path through this scanner. The batch CLI rejects that combination before staging backups or starting Maya. Stop on the reported error; do not move, rename, or copy a scene after approval. A different Maya version requires a fresh scan and approval.
- Use a fresh, not-yet-existing `.json` path for every `--report`; keep pre-scan, cleanup, and later scan evidence separate.

## Scan first

If a compatible CLI is not already available, show the user the exact repository, version, release asset, checksum asset, and installation destination. Obtain approval before downloading. Then run the Skill-local installer with that exact version:

```powershell
& "<skill-directory>\scripts\install_cli.ps1" -Version "<approved-version>"
```

The installer accepts no implicit `latest`: it downloads the exact versioned ZIP and `SHA256SUMS` from `loonghao/maya_umbrella_scanner`, verifies SHA-256, refuses an existing destination, and validates the installed CLI contract. It installs to `%LOCALAPPDATA%\maya_umbrella_scanner\versions\<version>`; disclose that exact destination before approval and run it as the current user, never from an elevated administrator shell. Preserve its JSON output and use the returned executable path. Do not run a downloaded binary whose checksum or capability validation failed.

Run the portable CLI in non-mutating scan mode for every requested root:

```powershell
& "<cli-directory>\maya_umbrella.exe" scan --path "C:\scenes" --path "D:\shots\asset" --report "C:\temp\maya-umbrella-scan.json"
```

`--report` is optional for scan-only work but required when cleanup may follow, because cleanup binds its authorization to the exact paths and SHA-256 values in that report. Preserve stdout, exit status, report, the CLI path/version, and the stdout-only `report_file_sha256`. Report the resolved scope, detected files, and that exact report digest to the user.

Fail closed. A nonzero exit, unreadable target, missing scanner, malformed or incomplete report, or result that cannot distinguish "no matches" from a scanner failure is not a clean result. Stop without cleanup and describe the uncertainty.

## Authorize cleanup

Cleanup is destructive and requires informed approval after the scan. Before asking, show:

- the exact roots, infected-file list, source hashes, and `report_file_sha256` from the completed scan output;
- the scanner path and Maya version;
- that affected scenes are force-saved in place and backed up by default under adjacent `_virus` directories;
- that read-only Maya discovery aborts when it finds infected reference files or infected files outside the approved scene manifest; those findings require a separate explicit scope, and the cleanup engine is prevented from modifying them;
- that infected nodes and script jobs in opened scenes may be removed; and
- that cleanup uses an empty `Maya.env`, an isolated temporary `MAYA_APP_DIR`, and disabled Python user-site, so existing user `Maya.env`, `userSetup.py`, `userSetup.mel`, `.pth`/`sitecustomize.py`, and custom startup paths are not executed or removed.

Do not treat a prior request to scan, the presence of `--confirm-clean`, or generic authorization to "fix it" as approval of an undisclosed file list. Obtain explicit approval for the presented scope and effects. Never set `MAYA_UMBRELLA_IGNORE_BACKUP=true`. If an existing `_virus` backup could be overwritten, stop and agree on preserving it before cleanup.

After approval, invoke `clean` with the same executable and paths used for the accepted scan. Pass the unchanged scan report through `--approved-scan-report` and the digest the user accepted through `--approved-scan-report-sha256`; the batch, legacy scanner, and Maya runner layers abort before mutation if the report bytes, target, infected path, or source hash has changed. These two approval arguments, `--maya-version`, and `--confirm-clean` are mandatory:

```powershell
& "<cli-directory>\maya_umbrella.exe" clean --path "C:\scenes" --path "D:\shots\asset" --maya-version 2024 --approved-scan-report "C:\temp\maya-umbrella-scan.json" --approved-scan-report-sha256 "<approved-report-sha256>" --confirm-clean --report "C:\temp\maya-umbrella-clean.json"
```

`--confirm-clean` is only a command-line guard. Supply it only after the user approval above.

## Verify the outcome

Before Maya starts, the batch CLI rejects symlinks, junctions, or reparse points in every approved target and scene path, then stages every expected `_virus` backup and verifies it against the approved source hash. The Maya runner reuses that exact backup and never overwrites it, then revalidates the source and backup immediately before saving; a redirected backup path, collision, identity alias, missing backup, or hash mismatch stops cleanup. It then performs one final scan across every accepted target after all cleanup attempts, including targets that were initially clean or skipped. Always run one additional independent `scan` with the same paths and executable after cleanup, writing a separate post-scan report. Do not claim success from the cleanup exit code alone.

Call the result clean only when cleanup completed without an indeterminate state, expected backups are present, the post-scan completed successfully across the full accepted scope, and it found no remaining signatures. Otherwise report partial cleanup or failure, list the unresolved files and side effects known to have occurred, and stop before retrying or changing scope.

An infection-free scene report does not prove that the user's Maya startup directories or Maya installation are clean. It also does not clear an infected reference or external file reported by Maya discovery. If any scope is unresolved, obtain fresh explicit approval before inspecting, quarantining, or cleaning it.
