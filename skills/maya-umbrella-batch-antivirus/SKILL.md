---
name: maya-umbrella-batch-antivirus
description: Scan and clean batches of Autodesk Maya .ma and .mb files on Windows with Maya Umbrella; use for suspected Maya malware or explicitly requested batch remediation, not general-purpose antivirus work.
---

# Maya Umbrella batch antivirus

Use this skill only on Windows with Python 3.9+, `maya_umbrella.exe`, and Autodesk Maya scene files. Cleanup also requires a locally installed Autodesk Maya version. Drive the operation through the bundled `scripts/batch_scan.py` helper; do not invoke cleanup directly through `maya_umbrella.exe`.

Before cleanup, run `maya_umbrella.exe --help` and require `--approved-scan-report`. The helper passes the approved evidence into the scanner so it rechecks paths and hashes immediately before starting Maya. If the flag is absent, stop and install a scanner release containing this contract; do not bypass it.

Read [the operation contract](references/operation-contract.md) before running a scan, interpreting a report, or proposing cleanup. It documents the helper arguments, backup behavior, and effects outside the requested scene roots.

## Establish the scope

- Resolve each requested `--path` to an absolute existing directory. Pass multiple targets by repeating `--path`; never broaden them with a shell glob or parent-directory substitution.
- Treat a drive root, user profile, shared production root, or other unusually broad target as unconfirmed until the user explicitly accepts that exact scope.
- Resolve `--scanner` to the intended `maya_umbrella.exe` when the helper cannot discover it unambiguously. Never download, replace, or switch scanner builds without permission.
- Keep each cleanup run on one explicitly selected Maya version. The scanner queries the selected `mayapy.exe` and refuses a different year, even when `MAYA_LOCATION` points elsewhere. Ensure no interactive Maya session is concurrently editing the target scenes.
- Maya 2019-2021 use Python 2 and cannot safely save a non-ASCII scene path through this scanner. The helper rejects that combination before staging backups or starting Maya. Stop on the reported error; do not move, rename, or copy a scene after approval. A different Maya version requires a fresh scan and approval.
- Use a fresh, not-yet-existing `.json` path for every `--report`; keep pre-scan, cleanup, and later scan evidence separate.

## Scan first

Run the helper in non-mutating scan mode for every requested root:

```powershell
python "<skill-directory>\scripts\batch_scan.py" scan --path "C:\scenes" --path "D:\shots\asset" --scanner "C:\tools\maya-umbrella\maya_umbrella.exe" --report "C:\temp\maya-umbrella-scan.json"
```

`--scanner` is optional when `maya_umbrella` resolves unambiguously. `--report` is optional for scan-only work but required when cleanup may follow, because cleanup binds its authorization to the exact paths and SHA-256 values in that report. Preserve stdout, exit status, report, and the stdout-only `report_file_sha256`. Report the resolved scope, detected files, and that exact report digest to the user.

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

After approval, invoke `clean` with the same paths and scanner used for the accepted scan. Pass the unchanged scan report through `--approved-scan-report` and the digest the user accepted through `--approved-scan-report-sha256`; both the helper and the scanner abort before mutation if the report bytes, target, infected path, or source hash has changed. These two approval arguments, `--maya-version`, and `--confirm-clean` are mandatory:

```powershell
python "<skill-directory>\scripts\batch_scan.py" clean --path "C:\scenes" --path "D:\shots\asset" --scanner "C:\tools\maya-umbrella\maya_umbrella.exe" --maya-version 2024 --approved-scan-report "C:\temp\maya-umbrella-scan.json" --approved-scan-report-sha256 "<approved-report-sha256>" --confirm-clean --report "C:\temp\maya-umbrella-clean.json"
```

`--confirm-clean` is only a command-line guard. Supply it only after the user approval above.

## Verify the outcome

Before Maya starts, the helper rejects symlinks, junctions, or reparse points in every approved target and scene path, then stages every expected `_virus` backup and verifies it against the approved source hash. The Maya runner reuses that exact backup and never overwrites it, then revalidates the source and backup immediately before saving; a redirected backup path, collision, identity alias, missing backup, or hash mismatch stops cleanup. It then performs one final scan across every accepted target after all cleanup attempts, including targets that were initially clean or skipped. Always run one additional independent `scan` with the same paths and scanner after cleanup, writing a separate post-scan report. Do not claim success from the cleanup exit code alone.

Call the result clean only when cleanup completed without an indeterminate state, expected backups are present, the post-scan completed successfully across the full accepted scope, and it found no remaining signatures. Otherwise report partial cleanup or failure, list the unresolved files and side effects known to have occurred, and stop before retrying or changing scope.

An infection-free scene report does not prove that the user's Maya startup directories or Maya installation are clean. It also does not clear an infected reference or external file reported by Maya discovery. If any scope is unresolved, obtain fresh explicit approval before inspecting, quarantining, or cleaning it.
