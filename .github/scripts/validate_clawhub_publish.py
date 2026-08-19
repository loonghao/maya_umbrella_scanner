"""Validate the structured receipt emitted by a pinned ClawHub CLI publish."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


EXPECTED_STATUSES = {
    "dry-run": frozenset({"unchanged", "would-publish"}),
    "publish": frozenset({"unchanged", "published", "pending-publication", "submitted"}),
}
FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}")


class ReceiptError(ValueError):
    """Raised when a ClawHub receipt cannot prove the requested operation."""


def _require_nonempty_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ReceiptError(f"ClawHub receipt is missing {field}")
    return value


def validate_receipt(
    payload: Any,
    mode: str,
    expected_slug: str,
    preview: Any | None = None,
) -> dict[str, Any]:
    """Return a validated receipt or fail closed on an unknown result contract."""
    if mode not in EXPECTED_STATUSES:
        raise ReceiptError(f"Unknown validation mode: {mode!r}")
    if not isinstance(payload, dict):
        raise ReceiptError("ClawHub receipt must be a JSON object")
    if payload.get("ok") is not True:
        raise ReceiptError("ClawHub receipt did not report ok=true")

    slug = payload.get("slug")
    if slug != expected_slug:
        raise ReceiptError(f"ClawHub receipt slug {slug!r} does not match {expected_slug!r}")

    status = payload.get("status")
    allowed = EXPECTED_STATUSES[mode]
    if not isinstance(status, str) or status not in allowed:
        raise ReceiptError(
            f"ClawHub status {status!r} is not valid for {mode}; expected one of {sorted(allowed)}"
        )

    version = _require_nonempty_string(payload, "version")
    fingerprint = _require_nonempty_string(payload, "fingerprint")
    if FINGERPRINT_PATTERN.fullmatch(fingerprint) is None:
        raise ReceiptError("ClawHub receipt fingerprint must be 64 lowercase hex characters")

    file_count = payload.get("fileCount")
    if isinstance(file_count, bool) or not isinstance(file_count, int) or file_count <= 0:
        raise ReceiptError("ClawHub receipt fileCount must be a positive integer")

    if "latestVersion" not in payload:
        raise ReceiptError("ClawHub receipt is missing latestVersion")
    latest_version = payload["latestVersion"]
    if latest_version is not None and (
        not isinstance(latest_version, str) or not latest_version.strip()
    ):
        raise ReceiptError("ClawHub receipt latestVersion must be a version or null")
    if status == "unchanged" and latest_version != version:
        raise ReceiptError(
            "Unchanged receipt does not match the public latestVersion; "
            "the matching bundle may be pending or historical"
        )

    if status == "pending-publication":
        if payload.get("publicationStatus") != "pending":
            raise ReceiptError("Pending publication receipt must report publicationStatus=pending")
        _require_nonempty_string(payload, "versionId")
        # Repository policy requires a moderation handle even though the CLI type is optional.
        _require_nonempty_string(payload, "attemptId")
    elif status == "published":
        if payload.get("publicationStatus") != "published":
            raise ReceiptError("Published receipt must report publicationStatus=published")
        _require_nonempty_string(payload, "versionId")
    elif status == "submitted":
        _require_nonempty_string(payload, "versionId")

    if preview is not None:
        validated_preview = validate_receipt(preview, "dry-run", expected_slug)
        for field in ("slug", "version", "fingerprint", "fileCount"):
            if payload.get(field) != validated_preview.get(field):
                raise ReceiptError(f"ClawHub receipt {field} does not match the dry-run preview")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--mode", choices=tuple(EXPECTED_STATUSES), required=True)
    parser.add_argument("--expected-slug", required=True)
    parser.add_argument("--preview", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = json.loads(args.receipt.read_text(encoding="utf-8"))
        preview = (
            json.loads(args.preview.read_text(encoding="utf-8")) if args.preview else None
        )
        if args.mode == "publish" and preview is None:
            raise ReceiptError("Publish validation requires the dry-run preview")
        receipt = validate_receipt(payload, args.mode, args.expected_slug, preview)
    except (OSError, json.JSONDecodeError, ReceiptError) as error:
        raise SystemExit(f"Invalid ClawHub publish receipt: {error}") from error

    print(
        "ClawHub receipt accepted: "
        f"{receipt['slug']}@{receipt['version']} status={receipt['status']} mode={args.mode}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
