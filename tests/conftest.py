from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs"
M0_MATCH = CONFIGS / "matches" / "m0.yaml"


@pytest.fixture
def m0_match() -> Path:
    return M0_MATCH
