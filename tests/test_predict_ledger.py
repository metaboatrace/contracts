"""predict-ledger レコード契約の wire 型テスト.

このパッケージが契約 (Published Language) の **正本**。ml (producer) は「この golden を
produce できる」、dashboard (consumer) は「この golden を consume できる」という薄い適合
テストだけを各リポに置き、両者がこの同一サンプルに conform する。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from metaboatrace.contracts.predict_ledger import (
    HELD_ON_INDEX,
    PredictLedgerRecord,
    PredictOutcome,
)

# このシステムの時刻はすべて JST 基準。
_JST = timezone(timedelta(hours=9))

# 黄金サンプル: 正常終了・買い目あり (実レース 202606070710 / staging / 1点 / ¥700)。
# ml の produce テスト・dashboard の consume テストと **リテラル一致** させること。
GOLDEN_OK_BETS = {
    "race_id": "202606070710",
    "held_on": "2026-06-07",
    "outcome": "ok_bets",
    "n_bets": 1,
    "total_amount": 700,
    "model_version": "staging",
    "decided_at": "2026-06-07T19:46:18+09:00",
}

# 異常終了サンプル: decided_at は無く error_class が載る。
GOLDEN_ERROR = {
    "race_id": "202606070710",
    "held_on": "2026-06-07",
    "outcome": "error",
    "n_bets": 0,
    "total_amount": 0,
    "model_version": "staging",
    "error_class": "OddsUnavailable",
}


def test_held_on_index_constant() -> None:
    assert HELD_ON_INDEX == "held_on-index"


def test_parses_golden_ok_bets() -> None:
    record = PredictLedgerRecord.model_validate(GOLDEN_OK_BETS)

    assert record.race_id == "202606070710"
    assert record.held_on == "2026-06-07"
    assert record.outcome is PredictOutcome.OK_BETS
    assert record.n_bets == 1
    assert record.total_amount == 700
    assert record.model_version == "staging"
    assert record.decided_at == datetime(2026, 6, 7, 19, 46, 18, tzinfo=_JST)
    assert record.error_class is None


def test_parses_golden_error() -> None:
    record = PredictLedgerRecord.model_validate(GOLDEN_ERROR)

    assert record.outcome is PredictOutcome.ERROR
    assert record.error_class == "OddsUnavailable"
    assert record.decided_at is None


def test_round_trips_to_same_wire() -> None:
    # produce 側 (model → JSON) と consume 側 (JSON → model) が同一 wire で閉じる。
    # decided_at / error_class が None の optional は wire に出さない (DynamoDB は None を嫌う)。
    record = PredictLedgerRecord.model_validate(GOLDEN_OK_BETS)
    dumped = json.loads(record.model_dump_json(exclude_none=True))

    assert dumped == GOLDEN_OK_BETS


def test_outcome_enum_values_cover_ledger_vocabulary() -> None:
    assert {o.value for o in PredictOutcome} == {"ok_bets", "ok_nobets", "error"}


def test_rejects_unknown_outcome() -> None:
    # enum の網羅は契約が所有。未知の結末は drift として reject する。
    with pytest.raises(ValidationError):
        PredictLedgerRecord.model_validate({**GOLDEN_OK_BETS, "outcome": "timeout"})


def test_rejects_unknown_top_level_key() -> None:
    # extra="forbid": 未知キーは drift として reject (黙って捨てない)。
    with pytest.raises(ValidationError):
        PredictLedgerRecord.model_validate({**GOLDEN_OK_BETS, "dry_run": True})


def test_rejects_negative_n_bets() -> None:
    with pytest.raises(ValidationError):
        PredictLedgerRecord.model_validate({**GOLDEN_OK_BETS, "n_bets": -1})


def test_rejects_negative_total_amount() -> None:
    with pytest.raises(ValidationError):
        PredictLedgerRecord.model_validate({**GOLDEN_OK_BETS, "total_amount": -1})


def test_rejects_missing_required_key() -> None:
    payload = {k: v for k, v in GOLDEN_OK_BETS.items() if k != "outcome"}
    with pytest.raises(ValidationError):
        PredictLedgerRecord.model_validate(payload)
