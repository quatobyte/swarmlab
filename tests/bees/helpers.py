from pathlib import Path

from swarmlab.bees.params import BeesParams
from swarmlab.core.config import load_match

CONFIGS = Path(__file__).resolve().parents[2] / "configs"


def bees_params(
    profile: str = "small", seed: int = 42, overrides: tuple[str, ...] = ()
) -> BeesParams:
    cfg = load_match(
        CONFIGS / "matches" / "m0.yaml",
        cli_overrides=(f"profile={profile}", f"seed={seed}", "hives=[]", *overrides),
    )
    return BeesParams.model_validate(cfg.params)
