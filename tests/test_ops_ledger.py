"""ops-ledger レコード契約の wire 型テスト.

このパッケージが契約 (Published Language) の **正本**。voting / ml / infra (producer) は
「この golden を produce できる」、突合バッチ (consumer) は「この golden を consume できる」
という薄い適合テストだけを各リポに置き、両者がこの同一サンプルに conform する。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from metaboatrace.contracts.ops_ledger import (
    JobOutcome,
    OpsEntryKind,
    OpsLedgerRecord,
)

# wire の instant は UTC (時刻の取り扱い標準)。_JST は instant 同一性の確認用。
_JST = timezone(timedelta(hours=9))

# 黄金サンプル: 日次の入金工程が正常終了。instant は wire 正準の UTC。producer の produce
# テスト・突合バッチの consume テストと **リテラル一致** させること。
GOLDEN_JOB = {
    "date": "2026-04-27",
    "entry_id": "job#deposit",
    "kind": "job",
    "outcome": "ok",
    "recorded_at": "2026-04-27T23:30:12+00:00",
}

# ノブ変更のサンプル: outcome は載らず value が載る。entry_id に JST の時刻を含む。
GOLDEN_KNOB = {
    "date": "2026-04-27",
    "entry_id": "knob#/metaboatrace/production/voting/DRY_RUN#083012",
    "kind": "knob",
    "value": "false",
    "recorded_at": "2026-04-26T23:30:12+00:00",
}


def test_entry_kind_enum_values_cover_ledger_vocabulary() -> None:
    assert {k.value for k in OpsEntryKind} == {"job", "knob"}


def test_job_outcome_enum_values_cover_vocabulary() -> None:
    assert {o.value for o in JobOutcome} == {"ok", "failed", "unknown", "skipped"}


def test_parses_golden_job() -> None:
    record = OpsLedgerRecord.model_validate(GOLDEN_JOB)

    assert record.date == "2026-04-27"
    assert record.entry_id == "job#deposit"
    assert record.kind is OpsEntryKind.JOB
    assert record.outcome == JobOutcome.OK
    assert record.value is None
    assert record.detail is None
    assert record.recorded_at == datetime(2026, 4, 28, 8, 30, 12, tzinfo=_JST)


def test_parses_golden_knob() -> None:
    record = OpsLedgerRecord.model_validate(GOLDEN_KNOB)

    assert record.kind is OpsEntryKind.KNOB
    assert record.outcome is None
    assert record.value == "false"


def test_job_round_trips_to_same_wire() -> None:
    # produce 側 (model → JSON) と consume 側 (JSON → model) が同一 wire で閉じる。
    # value / detail が None の optional は wire に出さない (DynamoDB は None を嫌う)。
    record = OpsLedgerRecord.model_validate(GOLDEN_JOB)
    dumped = json.loads(record.model_dump_json(exclude_none=True))

    assert dumped == GOLDEN_JOB


def test_knob_round_trips_to_same_wire() -> None:
    record = OpsLedgerRecord.model_validate(GOLDEN_KNOB)
    dumped = json.loads(record.model_dump_json(exclude_none=True))

    assert dumped == GOLDEN_KNOB


def test_rejects_unknown_kind() -> None:
    # enum の網羅は契約が所有。未知の種別は drift として reject する。
    with pytest.raises(ValidationError):
        OpsLedgerRecord.model_validate({**GOLDEN_JOB, "kind": "alarm"})


def test_rejects_unknown_top_level_key() -> None:
    # extra="forbid": 未知キーは drift として reject (黙って捨てない)。
    with pytest.raises(ValidationError):
        OpsLedgerRecord.model_validate({**GOLDEN_JOB, "race_id": "202604270805"})


def test_rejects_missing_required_key() -> None:
    payload = {k: v for k, v in GOLDEN_JOB.items() if k != "kind"}
    with pytest.raises(ValidationError):
        OpsLedgerRecord.model_validate(payload)


def test_rejects_naive_recorded_at() -> None:
    # instant は aware 必須。naive は wire で reject する。
    with pytest.raises(ValidationError):
        OpsLedgerRecord.model_validate({**GOLDEN_JOB, "recorded_at": "2026-04-27T23:30:12"})
