"""Tests for the fail-closed ClawHub publish receipt contract."""

# Import built-in modules
import importlib.util
from pathlib import Path

# Import third-party modules
import pytest


SCRIPT_PATH = Path(__file__).parents[1] / ".github" / "scripts" / "validate_clawhub_publish.py"
SPEC = importlib.util.spec_from_file_location("validate_clawhub_publish", SCRIPT_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def receipt(status):
    payload = {
        "ok": True,
        "status": status,
        "slug": "maya-umbrella-batch-antivirus",
        "version": "1.0.0",
        "latestVersion": "1.0.0" if status == "unchanged" else None,
        "fileCount": 3,
        "fingerprint": "a" * 64,
    }
    if status == "pending-publication":
        payload.update(
            publicationStatus="pending", versionId="version_1", attemptId="attempt_1"
        )
    elif status == "published":
        payload.update(publicationStatus="published", versionId="version_1")
    elif status == "submitted":
        payload.update(versionId="version_1")
    return payload


@pytest.mark.parametrize("status", ["unchanged", "would-publish"])
def test_dry_run_accepts_only_preview_results(status):
    assert VALIDATOR.validate_receipt(
        receipt(status), "dry-run", "maya-umbrella-batch-antivirus"
    )["status"] == status


@pytest.mark.parametrize(
    "status", ["unchanged", "published", "pending-publication", "submitted"]
)
def test_publish_accepts_uploaded_and_moderation_pending_results(status):
    assert VALIDATOR.validate_receipt(
        receipt(status), "publish", "maya-umbrella-batch-antivirus"
    )["status"] == status


@pytest.mark.parametrize("status", ["would-publish", "failed", "unexpected", None])
def test_publish_rejects_non_publish_or_unknown_results(status):
    with pytest.raises(VALIDATOR.ReceiptError, match="not valid for publish"):
        VALIDATOR.validate_receipt(receipt(status), "publish", "maya-umbrella-batch-antivirus")


def test_receipt_identity_and_success_are_required():
    wrong_slug = receipt("published")
    wrong_slug["slug"] = "another-skill"
    with pytest.raises(VALIDATOR.ReceiptError, match="does not match"):
        VALIDATOR.validate_receipt(wrong_slug, "publish", "maya-umbrella-batch-antivirus")

    failed = receipt("published")
    failed["ok"] = False
    with pytest.raises(VALIDATOR.ReceiptError, match="ok=true"):
        VALIDATOR.validate_receipt(failed, "publish", "maya-umbrella-batch-antivirus")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("fingerprint", "short", "fingerprint"),
        ("fileCount", 0, "fileCount"),
        ("fileCount", True, "fileCount"),
    ],
)
def test_receipt_requires_a_complete_bundle_identity(field, value, message):
    payload = receipt("would-publish")
    payload[field] = value
    with pytest.raises(VALIDATOR.ReceiptError, match=message):
        VALIDATOR.validate_receipt(payload, "dry-run", "maya-umbrella-batch-antivirus")


@pytest.mark.parametrize("latest_version", [None, "0.9.0"])
def test_unchanged_requires_the_matching_public_latest_version(latest_version):
    payload = receipt("unchanged")
    payload["latestVersion"] = latest_version
    with pytest.raises(VALIDATOR.ReceiptError, match="public latestVersion"):
        VALIDATOR.validate_receipt(payload, "dry-run", "maya-umbrella-batch-antivirus")


@pytest.mark.parametrize(
    ("status", "missing_field"),
    [
        ("pending-publication", "attemptId"),
        ("pending-publication", "versionId"),
        ("published", "versionId"),
        ("submitted", "versionId"),
    ],
)
def test_publish_receipt_requires_status_specific_evidence(status, missing_field):
    payload = receipt(status)
    del payload[missing_field]
    with pytest.raises(VALIDATOR.ReceiptError, match=missing_field):
        VALIDATOR.validate_receipt(payload, "publish", "maya-umbrella-batch-antivirus")


@pytest.mark.parametrize(
    ("status", "publication_status"),
    [("pending-publication", "published"), ("published", "pending")],
)
def test_publish_receipt_rejects_a_mismatched_publication_status(
    status, publication_status
):
    payload = receipt(status)
    payload["publicationStatus"] = publication_status
    with pytest.raises(VALIDATOR.ReceiptError, match="publicationStatus"):
        VALIDATOR.validate_receipt(payload, "publish", "maya-umbrella-batch-antivirus")


@pytest.mark.parametrize("field", ["version", "fingerprint", "fileCount"])
def test_publish_receipt_must_match_the_preview(field):
    preview = receipt("would-publish")
    published = receipt("published")
    published[field] = {
        "version": "1.0.1",
        "fingerprint": "b" * 64,
        "fileCount": 4,
    }[field]
    with pytest.raises(VALIDATOR.ReceiptError, match=f"{field} does not match"):
        VALIDATOR.validate_receipt(
            published,
            "publish",
            "maya-umbrella-batch-antivirus",
            preview,
        )
