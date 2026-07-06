"""Unit tests for core.economy and core.recommender."""
from tft_companion.core import economy
from tft_companion.core.models import (
    Champion, CompUnit, GameState, MetaComp, Role, SetData,
)
from tft_companion.core.recommender import RecommendationEngine


def make_set() -> SetData:
    champs = {
        "Ahri": Champion(id="Ahri", name="Ahri", cost=4, traits=("Mage", "Spirit")),
        "Nasus": Champion(id="Nasus", name="Nasus", cost=1, traits=("Guardian",)),
        "Kled": Champion(id="Kled", name="Kled", cost=2, traits=("Mage",)),
        "Garen": Champion(id="Garen", name="Garen", cost=1, traits=("Knight",)),
    }
    return SetData(
        set_id="t", patch="0", champions=champs,
        pool_sizes={1: 30, 2: 25, 3: 18, 4: 10, 5: 9},
        shop_odds={7: {1: 0.19, 2: 0.30, 3: 0.40, 4: 0.10, 5: 0.01},
                   8: {1: 0.16, 2: 0.21, 3: 0.30, 4: 0.30, 5: 0.03}},
        xp_to_next_level={7: 48, 8: 80},
    )


def target_comp() -> MetaComp:
    return MetaComp(
        id="c", name="Test Comp",
        units=(
            CompUnit("Ahri", Role.CARRY),
            CompUnit("Nasus", Role.CORE),
        ),
    )


# ---------------------------------------------------------------- economy
def test_interest_and_income():
    assert economy.interest(47) == 4
    assert economy.interest(80) == 5  # capped
    assert economy.round_income(gold=50, streak=0) == 10
    assert economy.round_income(gold=23, streak=-4) == 5 + 2 + 2


def test_interest_breakpoint():
    assert economy.next_interest_breakpoint(47) == 3
    assert economy.next_interest_breakpoint(50) is None


def test_gold_to_next_level():
    sd = make_set()
    state = GameState(level=7, xp=30)  # missing 18 xp -> 5 purchases -> 20 gold
    assert economy.gold_to_next_level(state, sd) == 20


def test_advise_returns_something_sane():
    sd = make_set()
    tips = economy.advise(GameState(level=7, gold=52, health=20), sd)
    severities = {t.severity for t in tips}
    assert "danger" in severities  # low HP flagged


# ------------------------------------------------------------- recommender
def test_recommender_ranks_comp_units_first():
    sd = make_set()
    engine = RecommendationEngine()
    state = GameState(
        level=8, gold=30,
        owned={"Ahri": 2},
        shop=["Garen", "Ahri", "Kled", None, "Ahri"],
    )
    recs = engine.recommend_shop(state, sd, target_comp())
    assert recs, "expected recommendations"
    top = recs[0]
    assert top.champion_id == "Ahri"
    assert top.slots == (1, 4)
    assert any("estrella" in r for r in top.reasons)      # upgrade proximity
    assert any("carry" in r for r in top.reasons)          # role
    # Kled shares the Mage trait with Ahri -> gets synergy points, Garen none
    ids = [r.champion_id for r in recs]
    assert "Kled" in ids and "Garen" not in ids


def test_recommender_without_target_still_values_upgrades():
    sd = make_set()
    engine = RecommendationEngine()
    state = GameState(level=8, gold=10, owned={"Garen": 2}, shop=["Garen"] + [None] * 4)
    recs = engine.recommend_shop(state, sd, target=None)
    assert recs and recs[0].champion_id == "Garen"


def test_roll_or_level_suggests_leveling_for_high_cost_comps():
    sd = make_set()
    engine = RecommendationEngine()
    tips = engine.roll_or_level(GameState(level=7, gold=40, health=80), sd, target_comp())
    assert any("subir de nivel" in t for t in tips)
