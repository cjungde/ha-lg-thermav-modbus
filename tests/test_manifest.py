"""Static validation of the integration's manifest and HACS metadata.

These tests have no Home Assistant dependency, so they run fast in CI and
catch the most common packaging mistakes (malformed JSON, domain mismatch,
missing required manifest keys). Add Home Assistant based tests alongside
these as the integration grows.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENTS_DIR = REPO_ROOT / "custom_components"

# Keys Home Assistant requires for a config-flow custom integration.
REQUIRED_MANIFEST_KEYS = {
    "domain",
    "name",
    "version",
    "documentation",
    "codeowners",
    "iot_class",
}


def _integration_dir() -> Path:
    candidates = [
        p for p in COMPONENTS_DIR.iterdir() if (p / "manifest.json").is_file()
    ]
    assert len(candidates) == 1, f"expected exactly one integration, found {candidates}"
    return candidates[0]


def test_manifest_is_valid_json() -> None:
    manifest = json.loads((_integration_dir() / "manifest.json").read_text())
    assert isinstance(manifest, dict)


def test_domain_matches_folder_name() -> None:
    integration = _integration_dir()
    manifest = json.loads((integration / "manifest.json").read_text())
    assert manifest["domain"] == integration.name


def test_required_manifest_keys_present() -> None:
    manifest = json.loads((_integration_dir() / "manifest.json").read_text())
    missing = REQUIRED_MANIFEST_KEYS - manifest.keys()
    assert not missing, f"manifest.json is missing keys: {sorted(missing)}"


def test_version_is_non_empty_string() -> None:
    manifest = json.loads((_integration_dir() / "manifest.json").read_text())
    assert isinstance(manifest["version"], str) and manifest["version"]


def test_codeowners_is_non_empty_list() -> None:
    manifest = json.loads((_integration_dir() / "manifest.json").read_text())
    assert isinstance(manifest["codeowners"], list) and manifest["codeowners"]


def test_hacs_json_is_valid() -> None:
    hacs = json.loads((REPO_ROOT / "hacs.json").read_text())
    assert hacs.get("name")
