"""Distribution metadata must retain the browser UI used by the service."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_web_assets_are_declared_as_package_data() -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    patterns = config["tool"]["setuptools"]["package-data"]["supra_agentic"]
    assert {"web/*.html", "web/*.css", "web/*.js"} <= set(patterns)
