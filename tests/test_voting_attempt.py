"""voting-attempt-log レコード契約の wire 型テスト.

このパッケージが契約 (Published Language) の **正本**。voting / infra recorder / 手動照合
(producer) は「この golden を produce できる」、突合バッチ (consumer) は「この golden を
consume できる」という薄い適合テストだけを各リポに置き、両者がこの同一サンプルに conform する。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from metaboatrace.contracts.voting_attempt import (
    HELD_ON_INDEX,
    VotingAttemptOutcome,
    VotingAttemptRecord,
)

# wire の instant は UTC (時刻の取り扱い標準)。_JST は instant 同一性の確認用。
_JST = timezone(timedelta(hours=9))

# 黄金サンプル: アプリが書く実弾の投票確定。instant は wire 正準の UTC。voting の produce
# テスト・突合バッチの consume テストと **リテラル一致** させること。
GOLDEN_PLACED = {
    "race_id": "202604270805",
    "run_id": "run-1",
    "held_on": "2026-04-27",
    "outcome": "placed",
    "dry_run": False,
    "attempted_at": "2026-04-27T11:55:05+00:00",
}

# recorder が書くサンプル: アプリ未到達なので dry_run は載らない。
GOLDEN_TASK_DIED = {
    "race_id": "202604270805",
    "run_id": "evt-8f6b1c3a-0000-4000-8000-000000000001",
    "held_on": "2026-04-27",
    "outcome": "task_died",
    "detail": "CannotPullContainerError",
    "attempted_at": "2026-04-27T11:54:00+00:00",
}


def test_held_on_index_constant() -> None:
    assert HELD_ON_INDEX == "held_on-index"


def test_outcome_enum_values_cover_attempt_vocabulary() -> None:
    assert {o.value for o in VotingAttemptOutcome} == {
        "placed",
        "dry_run",
        "duplicate",
        "kill_switch",
        "policy_blocked",
        "blocked_by_interlock",
        "failed",
        "unknown",
        "dispatch_failed",
        "task_died",
        "resolved_placed",
        "resolved_not_placed",
    }


def test_parses_golden_placed() -> None:
    record = VotingAttemptRecord.model_validate(GOLDEN_PLACED)

    assert record.race_id == "202604270805"
    assert record.run_id == "run-1"
    assert record.held_on == "2026-04-27"
    assert record.outcome is VotingAttemptOutcome.PLACED
    assert record.dry_run is False
    assert record.detail is None
    assert record.attempted_at == datetime(2026, 4, 27, 20, 55, 5, tzinfo=_JST)


def test_parses_golden_task_died() -> None:
    record = VotingAttemptRecord.model_validate(GOLDEN_TASK_DIED)

    assert record.outcome is VotingAttemptOutcome.TASK_DIED
    assert record.dry_run is None
    assert record.detail == "CannotPullContainerError"


def test_round_trips_to_same_wire() -> None:
    # produce 側 (model → JSON) と consume 側 (JSON → model) が同一 wire で閉じる。
    # detail が None の optional は wire に出さない (DynamoDB は None を嫌う)。
    record = VotingAttemptRecord.model_validate(GOLDEN_PLACED)
    dumped = json.loads(record.model_dump_json(exclude_none=True))

    assert dumped == GOLDEN_PLACED


def test_dry_run_true_round_trips() -> None:
    # dry_run は False も wire に出す (exclude_none であって exclude_defaults ではない)。
    payload = {**GOLDEN_PLACED, "outcome": "dry_run", "dry_run": True}
    record = VotingAttemptRecord.model_validate(payload)

    assert record.outcome is VotingAttemptOutcome.DRY_RUN
    assert json.loads(record.model_dump_json(exclude_none=True)) == payload


def test_rejects_unknown_outcome() -> None:
    # enum の網羅は契約が所有。未知の結末は drift として reject する。
    with pytest.raises(ValidationError):
        VotingAttemptRecord.model_validate({**GOLDEN_PLACED, "outcome": "timeout"})


def test_rejects_unknown_top_level_key() -> None:
    # extra="forbid": 未知キーは drift として reject (黙って捨てない)。
    with pytest.raises(ValidationError):
        VotingAttemptRecord.model_validate({**GOLDEN_PLACED, "amount": 700})


def test_rejects_missing_required_key() -> None:
    payload = {k: v for k, v in GOLDEN_PLACED.items() if k != "run_id"}
    with pytest.raises(ValidationError):
        VotingAttemptRecord.model_validate(payload)


def test_rejects_naive_attempted_at() -> None:
    # instant は aware 必須。naive は wire で reject する。
    with pytest.raises(ValidationError):
        VotingAttemptRecord.model_validate({**GOLDEN_PLACED, "attempted_at": "2026-04-27T11:55:05"})
