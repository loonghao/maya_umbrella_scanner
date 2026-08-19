# ADR 0001: Ship a portable embedded-Python CLI and keep Maya repair in mayapy

- Status: Accepted
- Date: 2026-08-19

## Context

The Agent Skill needs one stable command-line contract that it can download, verify, and invoke on Windows without first provisioning Python. The scanner already has two materially different execution environments:

1. recursive signature discovery and guarded batch orchestration; and
2. scene repair through Autodesk Maya commands and the `maya-umbrella` engine inside the exact installed Maya version's `mayapy.exe`.

A full Rust rewrite would not remove the second environment. Rust cannot replace Maya's supported Python commands for opening, inspecting, and saving `.ma`/`.mb` scenes, so a rewritten executable would still have to launch a Python runner inside Maya. Reimplementing the approval, report, path, backup, and hash contracts in both Rust and Python would also create two security-critical sources of truth before a demonstrated runtime need exists.

## Decision

Ship a versioned Windows portable CLI bundle built with PyOxidizer. The bundle embeds the scanner's Python runtime and dependencies and exposes one executable contract:

```text
maya_umbrella.exe --version
maya_umbrella.exe scan  --path ... --report ...
maya_umbrella.exe clean --path ... --approved-scan-report ...
```

`scan` and `clean` implement batch orchestration inside the embedded runtime. When they need the existing single-root scanner path, they invoke the same executable without a subcommand. Cleanup then launches only the explicitly selected `mayapy.exe`, with the approved report digest, scene hashes, isolated Maya environment, and backup contract revalidated inside that process.

The release artifact is a portable folder archive rather than a single standalone PE: `maya_umbrella.exe` must remain beside its versioned `lib` and `bin` resources. The Skill installer downloads an exact GitHub Release version, verifies the archive against `SHA256SUMS`, installs to a fresh versioned directory, and probes the CLI contract. It never selects `latest` or overwrites a prior installation implicitly.

Release Please is the sole product-version and GitHub Release owner. The tag workflow builds the portable archive and only attaches hash-verified assets to the existing Release.

## Consequences

- End users and agents do not need system Python.
- Cleanup still requires Autodesk Maya because Maya owns the scene serialization API.
- The existing, tested safety contract remains shared by source installs and the portable executable.
- The distribution is larger than a native Rust launcher and must be installed as a directory.
- A release is usable by the Skill only after its ZIP, checksum, version output, and batch help pass verification.

## Alternatives considered

### Full Rust rewrite

Rejected for now. It would replace only discovery/orchestration while retaining the Maya Python runner, duplicate security-sensitive behavior, and delay the portable CLI outcome. Reconsider it only with measured evidence such as unacceptable startup time, archive size, memory usage, or a required deployment platform PyOxidizer cannot support. Any future Rust front end must consume the same report schema and pass the same fail-closed conformance and real-Maya E2E suite before replacing this implementation.

### Require a user-managed Python environment

Rejected. It adds interpreter and dependency drift to incident-response work and prevents the Skill from relying on one versioned executable contract.

### Keep batch orchestration as a Skill-local Python script

Rejected. It makes the Skill depend on system Python and lets the script and released scanner evolve independently. Embedding it in the product CLI gives releases and tests one ownership boundary.
