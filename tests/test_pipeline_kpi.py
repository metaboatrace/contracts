"""パイプライン歩留まり KPI 契約の wire 型テスト.

このパッケージが契約 (Published Language) の **正本**。突合バッチ (producer) は「この golden を
produce できる」、dashboard (consumer) は「この golden を consume できる」という薄い適合
テストだけを各リポに置き、両者がこの同一サンプルに conform する。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from metaboatrace.contracts.pipeline_kpi import (
    EXCLUDED_CATEGORIES,
    GOOD_CATEGORIES,
    SUMMARY_SORT_KEY,
    DailyKpiSummary,
    RaceKpiCategory,
    RaceKpiRecord,
)

# wire の instant は UTC (時刻の取り扱い標準)。_JST は instant 同一性の確認用。
_JST = timezone(timedelta(hours=9))

# 黄金サンプル: 実弾で完走した良品。instant は wire 正準の UTC。突合バッチの produce
# テスト・dashboard の consume テストと **リテラル一致** させること。
GOLDEN_GOOD_PLACED = {
    "held_on": "2026-04-27",
    "race_id": "202604270805",
    "category": "good_placed",
    "dry_run": False,
    "source": "attempt-log",
    "finalized_at": "2026-04-27T23:30:00+00:00",
}

# 無記録ロスのサンプル: voting に到達していないので dry_run は載らない。
GOLDEN_MISSING = {
    "held_on": "2026-04-27",
    "race_id": "202604270806",
    "category": "missing",
    "detail": "no record in any ledger",
    "source": "reconciliation",
    "finalized_at": "2026-04-27T23:30:00+00:00",
}

# 日次サマリのサンプル: 分母 = 3 (期待 4 − CANCELED 1)、良品 2 → 歩留まり 2/3。
GOLDEN_SUMMARY = {
    "held_on": "2026-04-27",
    "expected_races": 4,
    "counts": {
        "good_placed": 2,
        "canceled": 1,
        "missing": 1,
    },
    "yield_rate": 0.6666666666666666,
    "unknown_rate": 0.0,
    "finalized_at": "2026-04-27T23:30:00+00:00",
}


def test_summary_sort_key_constant() -> None:
    # サマリ item の range key は数字始まりの race_id と衝突しない値であること。
    assert SUMMARY_SORT_KEY == "_SUMMARY"
    assert not SUMMARY_SORT_KEY[0].isdigit()


def test_category_enum_values_cover_taxonomy() -> None:
    assert {c.value for c in RaceKpiCategory} == {
        "good_placed",
        "good_would_place",
        "good_nobets",
        "canceled",
        "suppressed_kill_switch",
        "suppressed_interlock",
        "loss_crawl",
        "loss_delivery_ml",
        "loss_predict",
        "loss_delivery_voting",
        "loss_deadline",
        "loss_vote_failed",
        "unknown_vote",
        "missing",
    }


def test_good_categories_match_good_prefix() -> None:
    # 分子の集合定義が enum の分類とずれないこと (片方だけ足す事故の検知)。
    assert frozenset(c for c in RaceKpiCategory if c.value.startswith("good_")) == GOOD_CATEGORIES


def test_excluded_categories_are_canceled_and_suppressed() -> None:
    expected = frozenset(
        c
        for c in RaceKpiCategory
        if c is RaceKpiCategory.CANCELED or c.value.startswith("suppressed_")
    )

    assert expected == EXCLUDED_CATEGORIES


def test_good_and_excluded_are_disjoint() -> None:
    # 良品と分母除外は排他 (同じ分類が分子と除外の両方に入らない)。
    assert not (GOOD_CATEGORIES & EXCLUDED_CATEGORIES)


def test_loss_and_special_categories_stay_in_denominator() -> None:
    # ロス・UNKNOWN_VOTE・MISSING は分母に残る (除外集合に含めない)。
    in_denominator = set(RaceKpiCategory) - EXCLUDED_CATEGORIES
    assert RaceKpiCategory.UNKNOWN_VOTE in in_denominator
    assert RaceKpiCategory.MISSING in in_denominator
    assert all(c in in_denominator for c in RaceKpiCategory if c.value.startswith("loss_"))


def test_parses_golden_good_placed() -> None:
    record = RaceKpiRecord.model_validate(GOLDEN_GOOD_PLACED)

    assert record.held_on == "2026-04-27"
    assert record.race_id == "202604270805"
    assert record.category is RaceKpiCategory.GOOD_PLACED
    assert record.dry_run is False
    assert record.detail is None
    assert record.source == "attempt-log"
    assert record.finalized_at == datetime(2026, 4, 28, 8, 30, 0, tzinfo=_JST)


def test_parses_golden_missing() -> None:
    record = RaceKpiRecord.model_validate(GOLDEN_MISSING)

    assert record.category is RaceKpiCategory.MISSING
    assert record.dry_run is None
    assert record.detail == "no record in any ledger"


def test_race_record_round_trips_to_same_wire() -> None:
    # produce 側 (model → JSON) と consume 側 (JSON → model) が同一 wire で閉じる。
    record = RaceKpiRecord.model_validate(GOLDEN_GOOD_PLACED)
    dumped = json.loads(record.model_dump_json(exclude_none=True))

    assert dumped == GOLDEN_GOOD_PLACED


def test_rejects_unknown_category() -> None:
    # enum の網羅は契約が所有。未知の分類は drift として reject する。
    with pytest.raises(ValidationError):
        RaceKpiRecord.model_validate({**GOLDEN_GOOD_PLACED, "category": "good_enough"})


def test_rejects_unknown_top_level_key_on_race_record() -> None:
    # extra="forbid": 未知キーは drift として reject (黙って捨てない)。
    with pytest.raises(ValidationError):
        RaceKpiRecord.model_validate({**GOLDEN_GOOD_PLACED, "outcome": "placed"})


def test_rejects_missing_source() -> None:
    payload = {k: v for k, v in GOLDEN_GOOD_PLACED.items() if k != "source"}
    with pytest.raises(ValidationError):
        RaceKpiRecord.model_validate(payload)


def test_rejects_naive_finalized_at() -> None:
    # instant は aware 必須。naive は wire で reject する。
    with pytest.raises(ValidationError):
        RaceKpiRecord.model_validate({**GOLDEN_GOOD_PLACED, "finalized_at": "2026-04-27T23:30:00"})


def test_parses_golden_summary() -> None:
    summary = DailyKpiSummary.model_validate(GOLDEN_SUMMARY)

    assert summary.held_on == "2026-04-27"
    assert summary.expected_races == 4
    assert summary.counts == {"good_placed": 2, "canceled": 1, "missing": 1}
    assert summary.unknown_rate == 0.0
    assert summary.finalized_at == datetime(2026, 4, 28, 8, 30, 0, tzinfo=_JST)


def test_summary_round_trips_to_same_wire() -> None:
    summary = DailyKpiSummary.model_validate(GOLDEN_SUMMARY)
    dumped = json.loads(summary.model_dump_json(exclude_none=True))

    assert dumped == GOLDEN_SUMMARY


def test_summary_counts_keys_are_category_values() -> None:
    # counts のキーは enum の値であること (網羅は producer の責務なので部分集合で足りる)。
    summary = DailyKpiSummary.model_validate(GOLDEN_SUMMARY)
    assert set(summary.counts) <= {c.value for c in RaceKpiCategory}


def test_rejects_unknown_top_level_key_on_summary() -> None:
    with pytest.raises(ValidationError):
        DailyKpiSummary.model_validate({**GOLDEN_SUMMARY, "race_id": "202604270805"})


def test_rejects_negative_expected_races() -> None:
    with pytest.raises(ValidationError):
        DailyKpiSummary.model_validate({**GOLDEN_SUMMARY, "expected_races": -1})


def test_rejects_negative_count() -> None:
    with pytest.raises(ValidationError):
        DailyKpiSummary.model_validate({**GOLDEN_SUMMARY, "counts": {"good_placed": -1}})


def test_rejects_out_of_range_rate() -> None:
    # 歩留まり・UNKNOWN 率は 0.0–1.0。
    with pytest.raises(ValidationError):
        DailyKpiSummary.model_validate({**GOLDEN_SUMMARY, "yield_rate": 1.5})
    with pytest.raises(ValidationError):
        DailyKpiSummary.model_validate({**GOLDEN_SUMMARY, "unknown_rate": -0.1})
