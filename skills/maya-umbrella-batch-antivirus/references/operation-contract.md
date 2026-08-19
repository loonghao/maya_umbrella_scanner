# Operation contract

Read this reference before executing either portable CLI mode. Cleanup changes files and Maya state; the confirmation and verification requirements below are part of the contract, not optional suggestions.

## Portable CLI interface

Use the exact `maya_umbrella.exe` path returned by the Skill-local installer or explicitly approved by the user. The release bundle includes its runtime and must not depend on system Python. Quote every path. Each target uses its own `--path` argument.

Scan one or more targets:

```powershell
& "<cli-directory>\maya_umbrella.exe" scan `
  --path "C:\project\scenes" `
  --path "D:\shots\asset" `
  --report "C:\temp\maya-umbrella-scan.json"
```

Clean the exact scope accepted after scanning:

```powershell
& "<cli-directory>\maya_umbrella.exe" clean `
  --path "C:\project\scenes" `
  --path "D:\shots\asset" `
  --maya-version 2024 `
  --approved-scan-report "C:\temp\maya-umbrella-scan.json" `
  --approved-scan-report-sha256 "<approved-report-sha256>" `
  --confirm-clean `
  --report "C:\temp\maya-umbrella-clean.json"
```

Then run `scan` again with the same executable and `--path` values. Use a different `--report` path so the pre-scan, cleanup, and post-scan evidence remain independently inspectable.

Argument semantics:

- `scan` performs discovery only. It must never be replaced by `clean` as the first operation.
- `clean` invokes Maya standalone remediation and requires `--maya-version <year>`, `--approved-scan-report <path>`, `--approved-scan-report-sha256 <digest>`, and `--confirm-clean`.
- Repeat `--path` for each directory. Do not provide a delimiter-separated list.
- `--version`, `scan --help`, and `clean --help` must prove the exact executable supports this contract before scanning.
- `--report` writes auditable output. It is optional only for scan-only work; cleanup requires the approved scan report.
- Every `--report` destination must be a fresh `.json` path. The CLI refuses to overwrite an existing report or scene file.
- `scan --report` prints `report_file_sha256` after atomically publishing the exact report bytes. Show that digest with the findings during approval.
- `--approved-scan-report` and `--approved-scan-report-sha256` bind cleanup to the exact report bytes, scanner, targets, infected paths, and source SHA-256 values the user reviewed. Any detected drift aborts the full batch before mutation.
- Cleanup requires a scanner whose `clean --help` exposes both approval arguments. The batch command forwards the report into the embedded legacy scanner path so it repeats the binding check immediately before Maya starts; older scanners fail closed.
- `--confirm-clean` records that the caller passed the command guard; it does not replace the user's informed approval.

## What scan and cleanup do

Scan recursively checks only `.ma` and `.mb` files for Maya Umbrella signatures and excludes the reserved `_virus` backup/quarantine directory. The name is fixed so an arbitrary existing project subtree cannot be hidden from scanning. Scan should not modify scenes, though the CLI may create temporary output and the requested report.

Cleanup rejects symlinks, junctions, and reparse points in every approved target or scene path so a path cannot be redirected after approval. It then stages each adjacent `_virus\<filename>` backup with no-clobber creation and verifies its SHA-256 and file identity against the approved source bytes. Redirected backup directories and source/backup identity aliases are refused; the Maya runner reuses the verified backup instead of overwriting it. It proves that the selected `mayapy.exe` reports the requested Maya year, then starts it in standalone mode with an isolated temporary `MAYA_APP_DIR`, a private log root, and no inherited Maya/Python startup paths. It opens matching scenes with script-node execution disabled, removes collected scene malware, and force-saves affected scenes in place.

Maya 2019-2021 run Python 2 and cannot safely save a non-ASCII Windows scene path through the pinned scanner engine. The batch CLI rejects that combination before staging backups or starting Maya. Never work around that failure by moving, renaming, or copying a scene after approval; choose another installed Maya version only after a fresh scan and explicit approval.

Cleanup has additional Maya-visible scope that must remain bounded:

- a callback-free, read-only Maya discovery pass aborts before scene cleanup when it finds infected references or external Maya/Python files; scan and approve each reported file under a separate remediation scope, and never let the engine modify it outside an approved manifest;
- it can remove or rewrite infected scene nodes and kill infected script jobs; and
- saving through a newer Maya version can change scene compatibility.

Isolation pre-creates an empty `Maya.env`, disables Python user-site, and prevents existing `Maya.env`, `userSetup.py`, `userSetup.mel`, `.pth`/`sitecustomize.py`, module paths, plug-in paths, and custom script paths from running before remediation. Read-only discovery can report matching files in normal Maya/Python directories, but this operation does not modify them. Treat their inspection or quarantine as a separate scope requiring its own evidence and approval.

The `_virus` backup name is fixed and backups must not be disabled. Existing same-name backups are not versioned or overwritten: cleanup refuses the collision. Preserve or relocate an existing backup only with user approval, then rescan because moved infected backups can re-enter the searchable scope.

## Fail-closed interpretation

Treat every target as one of `infected`, `clean`, or `indeterminate`. `indeterminate` is a failure state, not a clean state.

Stop and report `indeterminate` when any target is unreadable, scanner or Maya discovery fails, a child process fails, the CLI cannot distinguish no signatures from a scanner error, output/report parsing fails, or the scan does not cover every accepted target. Do not silently retry with another executable, Maya version, target, or environment.

Cleanup is verified only when all of these are true:

1. The user approved the exact scan findings and disclosed side effects.
2. The cleanup CLI completed without an indeterminate target.
3. Expected scene backups exist and were not silently disabled.
4. The CLI's final full-scope scan and a separate post-clean scan completed over the same accepted paths.
5. The post-clean scan reports no remaining signatures.

If any condition fails, describe the result as partial or failed. Preserve the reports and enumerate what is known to have changed before asking whether to investigate or retry.
