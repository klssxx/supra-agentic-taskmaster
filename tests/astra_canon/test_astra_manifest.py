"""SUPRA-compatible ASTRA manifest sentinels."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "governance" / "ASTRA_CANON.yaml"
EXPECTED = {
    "ASTRA-001",
    "ASTRA-003",
    "ASTRA-017",
    "ASTRA-018",
    "ASTRA-019",
    "ASTRA-020",
    "ASTRA-024",
    "ASTRA-026",
    "ASTRA-028",
    "ASTRA-031",
    "ASTRA-033",
    "ASTRA-034",
}


def test_astra_034_supra_manifest_is_compatible_and_scoped():
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["scope"] == "SUPRA"
    assert "ASTRA_CANON.yaml version 1" in data["compatible_with"]
    assert {c["id"] for c in data["contracts"]} == EXPECTED
    for item in data["contracts"]:
        assert item["status"] in {"CANON", "CANON_WITH_LIMITATIONS", "RESEARCH_ONLY"}
        assert item["contract"] and item["implementation"] and item["tests"]
        assert all((ROOT / path).exists() for path in item["implementation"])
        assert all((ROOT / path).exists() for path in item["tests"])
        assert "limitations" in item


def test_astra_017_restricted_execution_is_not_scientific_validation_in_docs():
    docs = (ROOT / "docs" / "ASTRA_CANON.md").read_text(encoding="utf-8")
    assert "no demuestra que una hipótesis sea científicamente válida" in docs
