"""voting-ledger レコード契約の wire 型テスト.

このパッケージが契約 (Published Language) の **正本**。voting (producer) は「この golden を
produce できる」、dashboard (consumer) は「この golden を consume できる」という薄い適合
テストだけを各リポに置き、両者がこの同一サンプルに conform する。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from metaboatrace.contracts.voting_ledger import (
    HELD_ON_INDEX,
    Confirmation,
    VoteStatus,
    VotingLedgerRecord,
)

# wire の instant は UTC (時刻の取り扱い標準)。_JST は instant 同一性の確認用。
_JST = timezone(timedelta(hours=9))

# 黄金サンプル: 投票確定 (PLACED, 受付確証1件)。instant は wire 正準の UTC。voting の
# produce テスト・dashboard の consume テストと **リテラル一致** させること。
GOLDEN_PLACED = {
    "race_id": "202604270805",
    "held_on": "2026-04-27",
    "status": "placed",
    "claimed_at": "2026-04-27T11:55:00+00:00",
    "run_id": "run-1",
    "amount": 700,
    "placed_at": "2026-04-27T11:55:05+00:00",
    "confirmations": [
        {"acceptance_number": "A1", "accepted_at": "2026-04-27T11:55:05+00:00"},
    ],
}

# CLAIMED サンプル: 占有のみ。optional (placed_at / confirmations / failure_reason) は無い。
GOLDEN_CLAIMED = {
    "race_id": "202604270805",
    "held_on": "2026-04-27",
    "status": "claimed",
    "claimed_at": "2026-04-27T11:55:00+00:00",
    "run_id": "run-1",
    "amount": 700,
}


def test_held_on_index_constant() -> None:
    assert HELD_ON_INDEX == "held_on-index"


def test_parses_golden_placed() -> None:
    record = VotingLedgerRecord.model_validate(GOLDEN_PLACED)

    assert record.race_id == "202604270805"
    assert record.held_on == "2026-04-27"
    assert record.status is VoteStatus.PLACED
    assert record.claimed_at == datetime(2026, 4, 27, 20, 55, 0, tzinfo=_JST)
    assert record.run_id == "run-1"
    assert record.amount == 700
    assert record.placed_at == datetime(2026, 4, 27, 20, 55, 5, tzinfo=_JST)
    assert len(record.confirmations) == 1
    assert record.confirmations[0].acceptance_number == "A1"
    assert record.confirmations[0].raw is None
    assert record.failure_reason is None


def test_parses_golden_claimed() -> None:
    record = VotingLedgerRecord.model_validate(GOLDEN_CLAIMED)

    assert record.status is VoteStatus.CLAIMED
    assert record.placed_at is None
    assert record.confirmations == []
    assert record.failure_reason is None


def test_round_trips_placed_to_same_wire() -> None:
    # produce 側 (model → JSON) と consume 側 (JSON → model) が同一 wire で閉じる。
    record = VotingLedgerRecord.model_validate(GOLDEN_PLACED)
    dumped = json.loads(record.model_dump_json(exclude_none=True))

    assert dumped == GOLDEN_PLACED


def test_status_enum_values_cover_ledger_vocabulary() -> None:
    assert {s.value for s in VoteStatus} == {"claimed", "placed", "failed", "unknown"}


def test_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        VotingLedgerRecord.model_validate({**GOLDEN_PLACED, "status": "cancelled"})


def test_rejects_unknown_top_level_key() -> None:
    # extra="forbid": 未知キーは drift として reject (黙って捨てない)。
    with pytest.raises(ValidationError):
        VotingLedgerRecord.model_validate({**GOLDEN_PLACED, "outcome": "ok"})


def test_rejects_unknown_confirmation_key() -> None:
    bad = {
        **GOLDEN_PLACED,
        "confirmations": [{**GOLDEN_PLACED["confirmations"][0], "vendor": "telboat"}],
    }
    with pytest.raises(ValidationError):
        VotingLedgerRecord.model_validate(bad)


def test_rejects_negative_amount() -> None:
    with pytest.raises(ValidationError):
        VotingLedgerRecord.model_validate({**GOLDEN_PLACED, "amount": -1})


def test_confirmation_round_trips_raw() -> None:
    c = Confirmation.model_validate(
        {"acceptance_number": "A1", "accepted_at": "2026-04-27T11:55:05+00:00", "raw": "<xml/>"}
    )
    assert c.raw == "<xml/>"


def test_rejects_naive_instant() -> None:
    # instant は aware 必須。naive は wire で reject する。
    with pytest.raises(ValidationError):
        VotingLedgerRecord.model_validate({**GOLDEN_PLACED, "placed_at": "2026-04-27T11:55:05"})
