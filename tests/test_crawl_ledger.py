"""crawl-ledger レコード契約の wire 型テスト.

このパッケージが契約 (Published Language) の **正本**。crawlers (producer) は「この golden を
produce できる」、突合バッチ (consumer) は「この golden を consume できる」という薄い適合
テストだけを各リポに置き、両者がこの同一サンプルに conform する。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from metaboatrace.contracts.crawl_ledger import (
    HELD_ON_INDEX,
    CrawlLedgerRecord,
    CrawlOutcome,
)

# wire の instant は UTC (時刻の取り扱い標準)。_JST は instant 同一性の確認用。
_JST = timezone(timedelta(hours=9))

# 黄金サンプル: オッズのクロール成功。instant は wire 正準の UTC。crawlers の produce
# テスト・突合バッチの consume テストと **リテラル一致** させること。
GOLDEN_OK = {
    "race_id": "202604270805",
    "aspect": "trifecta-odds",
    "held_on": "2026-04-27",
    "outcome": "ok",
    "finished_at": "2026-04-27T11:50:00+00:00",
}

# 失敗サンプル: error_class が載る。
GOLDEN_FAILED = {
    "race_id": "202604270805",
    "aspect": "trifecta-odds",
    "held_on": "2026-04-27",
    "outcome": "failed",
    "error_class": "HTTPError",
    "finished_at": "2026-04-27T11:50:00+00:00",
}


def test_held_on_index_constant() -> None:
    assert HELD_ON_INDEX == "held_on-index"


def test_outcome_enum_values_cover_ledger_vocabulary() -> None:
    assert {o.value for o in CrawlOutcome} == {"ok", "failed", "canceled", "revoked"}


def test_parses_golden_ok() -> None:
    record = CrawlLedgerRecord.model_validate(GOLDEN_OK)

    assert record.race_id == "202604270805"
    assert record.aspect == "trifecta-odds"
    assert record.held_on == "2026-04-27"
    assert record.outcome is CrawlOutcome.OK
    assert record.error_class is None
    assert record.finished_at == datetime(2026, 4, 27, 20, 50, 0, tzinfo=_JST)


def test_parses_golden_failed() -> None:
    record = CrawlLedgerRecord.model_validate(GOLDEN_FAILED)

    assert record.outcome is CrawlOutcome.FAILED
    assert record.error_class == "HTTPError"


def test_round_trips_to_same_wire() -> None:
    # produce 側 (model → JSON) と consume 側 (JSON → model) が同一 wire で閉じる。
    # error_class が None の optional は wire に出さない (DynamoDB は None を嫌う)。
    record = CrawlLedgerRecord.model_validate(GOLDEN_OK)
    dumped = json.loads(record.model_dump_json(exclude_none=True))

    assert dumped == GOLDEN_OK


def test_accepts_all_aspects_as_plain_str() -> None:
    # aspect の enum 網羅は producer (crawlers) のドメイン。契約は str として通す。
    for aspect in ("races", "before-information", "trifecta-odds", "result"):
        record = CrawlLedgerRecord.model_validate({**GOLDEN_OK, "aspect": aspect})
        assert record.aspect == aspect


def test_rejects_unknown_outcome() -> None:
    # enum の網羅は契約が所有。未知の結末は drift として reject する。
    with pytest.raises(ValidationError):
        CrawlLedgerRecord.model_validate({**GOLDEN_OK, "outcome": "skipped"})


def test_rejects_unknown_top_level_key() -> None:
    # extra="forbid": 未知キーは drift として reject (黙って捨てない)。
    with pytest.raises(ValidationError):
        CrawlLedgerRecord.model_validate({**GOLDEN_OK, "retry_count": 1})


def test_rejects_missing_required_key() -> None:
    payload = {k: v for k, v in GOLDEN_OK.items() if k != "aspect"}
    with pytest.raises(ValidationError):
        CrawlLedgerRecord.model_validate(payload)


def test_rejects_naive_finished_at() -> None:
    # instant は aware 必須。naive は wire で reject する。
    with pytest.raises(ValidationError):
        CrawlLedgerRecord.model_validate({**GOLDEN_OK, "finished_at": "2026-04-27T11:50:00"})
