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


#: Ровная карта без деревьев и камней — чистые условия для физических тестов.
FLAT = ("world.terrain.max_relief=0", "world.trees.per_ha=0", "world.rocks.per_ha=0")
CALM = ("weather.enabled=false",)


def make_sim(
    *overrides: str, profile: str = "small", seed: int = 42, duration: float = 3600.0
):
    """Матч без демо-пчёл: тест сам рождает пчёл (`module.spawn`) и командует автопилоту."""
    from swarmlab.core.sim import Simulation

    cfg = load_match(
        CONFIGS / "matches" / "m0.yaml",
        cli_overrides=(
            f"profile={profile}",
            f"seed={seed}",
            f"duration_s={duration}",
            "hives=[]",
            "demo.bees=[]",
            *overrides,
        ),
    )
    return Simulation(cfg)


def run_for(sim, seconds: float, each_step=None) -> None:
    """Шагать `seconds` секунд симуляции, вызывая `each_step(sim)` после каждого шага."""
    steps = round(seconds / sim.clock.dt)
    for _ in range(steps):
        sim.step()
        if each_step is not None:
            each_step(sim)
