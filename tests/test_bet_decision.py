"""bet decision 契約 (schema v1) の wire 型テスト.

このパッケージが契約 (Published Language) の **正本**。ml (producer) は
「この golden を produce できる」、voting (consumer) は「この golden を consume できる」
という薄い適合テストだけを各リポに置き、両者がこの同一サンプルに conform する。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from metaboatrace.contracts.bet_decision import SCHEMA_VERSION, BetDecision

# このシステムの時刻はすべて JST 基準。
_JST = timezone(timedelta(hours=9))

# 契約 schema v1 の黄金サンプル (実レース 202606070710 / staging / 2-5-6 / ¥700)。
# 下流 voting の golden 消費テストと **リテラル一致** させること。
GOLDEN_V1 = {
    "schema_version": 1,
    "race_id": "202606070710",
    "portfolio": "staging",
    "decided_at": "2026-06-07T19:46:18+09:00",
    "deadline_at": "2026-06-07T20:00:00+09:00",
    "bets": [
        {
            "bet_type": "trifecta",
            "finishing_order": [2, 5, 6],
            "amount_yen": 700,
            "odds_at_decision": 155.6,
        }
    ],
}


def test_schema_version_constant_matches_golden() -> None:
    assert GOLDEN_V1["schema_version"] == SCHEMA_VERSION


def test_parses_golden_v1() -> None:
    decision = BetDecision.model_validate(GOLDEN_V1)

    assert decision.schema_version == 1
    assert decision.race_id == "202606070710"
    assert decision.portfolio == "staging"
    assert decision.decided_at == datetime(2026, 6, 7, 19, 46, 18, tzinfo=_JST)
    assert decision.deadline_at == datetime(2026, 6, 7, 20, 0, 0, tzinfo=_JST)
    assert len(decision.bets) == 1
    bet = decision.bets[0]
    assert bet.bet_type == "trifecta"
    assert bet.finishing_order == (2, 5, 6)  # 配列 → tuple、index 0 = 1着
    assert bet.amount_yen == 700
    assert bet.odds_at_decision == 155.6


def test_round_trips_to_same_wire() -> None:
    # produce 側 (model → JSON) と consume 側 (JSON → model) が同一 wire で閉じる。
    decision = BetDecision.model_validate(GOLDEN_V1)
    dumped = json.loads(decision.model_dump_json())

    assert dumped == GOLDEN_V1


def test_rejects_unknown_top_level_key() -> None:
    # extra="forbid": 未知キーは drift として reject (黙って捨てない)。
    with pytest.raises(ValidationError):
        BetDecision.model_validate({**GOLDEN_V1, "model_version": "staging"})


def test_rejects_unknown_bet_key() -> None:
    bad = {**GOLDEN_V1, "bets": [{**GOLDEN_V1["bets"][0], "odds": 155.6}]}
    with pytest.raises(ValidationError):
        BetDecision.model_validate(bad)


def test_rejects_other_schema_version() -> None:
    # Literal[1] tripwire: 別 major は parse 不能 (fail-safe reject)。
    with pytest.raises(ValidationError):
        BetDecision.model_validate({**GOLDEN_V1, "schema_version": 2})


def test_rejects_missing_deadline() -> None:
    payload = {k: v for k, v in GOLDEN_V1.items() if k != "deadline_at"}
    with pytest.raises(ValidationError):
        BetDecision.model_validate(payload)


def test_rejects_null_deadline() -> None:
    with pytest.raises(ValidationError):
        BetDecision.model_validate({**GOLDEN_V1, "deadline_at": None})


def test_rejects_empty_bets() -> None:
    with pytest.raises(ValidationError):
        BetDecision.model_validate({**GOLDEN_V1, "bets": []})


def test_rejects_non_positive_amount() -> None:
    bad = {**GOLDEN_V1, "bets": [{**GOLDEN_V1["bets"][0], "amount_yen": 0}]}
    with pytest.raises(ValidationError):
        BetDecision.model_validate(bad)


@pytest.mark.parametrize("order", [[2, 5], [2, 5, 6, 1]])
def test_rejects_wrong_finishing_order_length(order: list[int]) -> None:
    # 3連単は構造的に3要素 (tuple[int, int, int])。
    bad = {**GOLDEN_V1, "bets": [{**GOLDEN_V1["bets"][0], "finishing_order": order}]}
    with pytest.raises(ValidationError):
        BetDecision.model_validate(bad)
