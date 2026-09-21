"""SUPRA-compatible ASTRA manifest and governance sentinels."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "governance" / "ASTRA_CANON.yaml"

MASTER_SCOPED_SUPRA = {
    "ASTRA-001",
    "ASTRA-003",
    "ASTRA-006",
    "ASTRA-017",
    "ASTRA-018",
    "ASTRA-019",
    "ASTRA-020",
    "ASTRA-024",
    "ASTRA-026",
    "ASTRA-027",
    "ASTRA-028",
    "ASTRA-031",
    "ASTRA-033",
    "ASTRA-034",
}


def _manifest():
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def test_astra_034_supra_manifest_matches_master_scoped_contracts():
    data = _manifest()
    assert data["version"] == 1
    assert data["scope"] == "SUPRA"
    assert "ASTRA_CANON.yaml version 1" in data["compatible_with"]
    assert {c["id"] for c in data["contracts"]} == MASTER_SCOPED_SUPRA
    assert len(data["contracts"]) == 14
    for item in data["contracts"]:
        assert item["status"] in {"CANON", "CANON_WITH_LIMITATIONS", "RESEARCH_ONLY"}
        assert item["contract"] and item["implementation"] and item["tests"]
        assert all((ROOT / path).exists() for path in item["implementation"])
        assert all((ROOT / path).exists() for path in item["tests"])
        assert item["limitations"]


def test_astra_006_027_are_not_omitted_from_supra_manifest():
    by_id = {c["id"]: c for c in _manifest()["contracts"]}
    assert "ASTRA-006" in by_id
    assert "confidence_score" in " ".join(by_id["ASTRA-006"]["limitations"])
    assert "ASTRA-027" in by_id
    assert "NOT_ESTABLISHED" in " ".join(by_id["ASTRA-027"]["limitations"])


def test_astra_017_restricted_execution_is_not_scientific_validation_in_docs():
    docs = (ROOT / "docs" / "ASTRA_CANON.md").read_text(encoding="utf-8")
    assert "no demuestra que una hipótesis sea científicamente válida" in docs


def test_astra_034_manifest_does_not_claim_remote_ci_was_run():
    evidence = _manifest()["enforcement_evidence"]
    assert evidence["rule"] == "normative_status_is_not_runtime_enforcement"
    assert evidence["current_branch_remote_ci"] == "NOT_RUN"
