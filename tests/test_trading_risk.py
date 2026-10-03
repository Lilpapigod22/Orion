import pytest

from orion.trading import risk
from orion.trading.risk import AccountState, Limits, RiskError


def make(entry=100.0, stop=99.0, target=102.0, side="long", equity=1000.0, limits=None, positions=None, lost=0.0,
         decimals=5, max_lev=40):
    return risk.plan("BTC", side, entry, stop, target, AccountState(equity, positions or {}, lost), decimals, max_lev,
                     limits or Limits(), "testnet")


def test_a_normal_long_risks_exactly_two_percent():
    p = make()
    assert p.size == 20.0 and p.notional == 2000.0
    assert p.leverage == 6                       # 2000 $ in a third of the account
    assert p.risk_usd == pytest.approx(20.0) and p.reward_usd == pytest.approx(40.0)
    assert p.margin == pytest.approx(2000 / 6)
    assert p.liquidation == pytest.approx(100 * (1 - (1 / 6 - 1 / 80)))
    assert p.fees_usd == pytest.approx(1.8)
    assert not p.reduced and p.network == "testnet"


def test_a_tight_stop_is_capped_by_the_leverage_limit():
    p = make(stop=99.8)
    assert p.leverage == 10 and p.reduced
    assert p.risk_usd == pytest.approx(6.6667, abs=1e-3)


def test_the_liquidation_must_stay_well_beyond_the_stop():
    p = make(stop=92.0, target=116.0, limits=Limits(risk_pct=10, max_leverage=10, daily_loss_pct=50, max_positions=10))
    assert p.leverage == 7 and p.size == 7.0 and p.reduced
    assert p.liquidation < 92.0
    with pytest.raises(RiskError, match="ликвидацията"):
        make(stop=30.0, target=240.0)


def test_a_short():
    p = make(entry=100.0, stop=101.0, target=98.0, side="short")
    assert p.side == "short" and p.liquidation > 101.0 and p.risk_usd == pytest.approx(20.0)


@pytest.mark.parametrize("kwargs, words", [
    ({"stop": 101.0}, "При лонг"),
    ({"side": "short"}, "При шорт"),
    ({"positions": {"BTC": {}}}, "Вече имате позиция в Биткойн"),
    ({"positions": {"ETH": {}, "SOL": {}, "DOGE": {}}}, "лимитът"),
    ({"lost": 60.0}, "заключена до полунощ"),
    ({"lost": 45.0}, "може да мине днешния лимит"),
    ({"equity": 4.0}, "под минимума"),
    ({"equity": 0.0}, "няма пари"),
])
def test_refusals_say_why(kwargs, words):
    with pytest.raises(RiskError, match=words):
        make(**kwargs)


def test_rounding_follows_hyperliquid_rules():
    assert risk.round_price(84467.123, 5) == 84467.0
    assert risk.round_price(2667.054, 4) == 2667.1
    assert risk.round_price(118.4853, 2) == 118.49
    assert risk.round_size(0.123456, 5) == 0.12345
    assert risk.round_size(33.333339, 2) == 33.33
    assert risk.maintenance(40) == 0.0125
