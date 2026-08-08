"""CrawlCompleted イベント契約の wire 型テスト.

このパッケージが契約 (Published Language) の **正本**。crawlers (producer) は
「この golden を produce できる」、ml (consumer) は「この golden を consume できる」
という薄い適合テストだけを各リポに置き、両者がこの同一サンプルに conform する。
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from metaboatrace.contracts.crawl_completed import (
    DETAIL_TYPE,
    SOURCE,
    CrawlCompletedDetail,
)

# CrawlCompleted detail の黄金サンプル (場12 / 2026-05-07 / 5R / trifecta-odds)。
# crawlers の produce テスト・ml の consume テストと **リテラル一致** させること。
GOLDEN_DETAIL = {
    "aspect": "trifecta-odds",
    "stadium_tel_code": 12,
    "race_holding_date": "20260507",
    "race_number": 5,
}


def test_routing_constants() -> None:
    # EventBridge の Source / DetailType 定数が両側の合意値であること。
    assert SOURCE == "metaboatrace.crawlers"
    assert DETAIL_TYPE == "CrawlCompleted"


def test_parses_golden_detail() -> None:
    detail = CrawlCompletedDetail.model_validate(GOLDEN_DETAIL)

    assert detail.aspect == "trifecta-odds"
    assert detail.stadium_tel_code == 12
    assert detail.race_holding_date == "20260507"
    assert detail.race_number == 5


def test_round_trips_to_same_wire() -> None:
    # produce 側 (model → JSON) と consume 側 (JSON → model) が同一 wire で閉じる。
    detail = CrawlCompletedDetail.model_validate(GOLDEN_DETAIL)
    dumped = json.loads(detail.model_dump_json())

    assert dumped == GOLDEN_DETAIL


def test_rejects_unknown_key() -> None:
    # extra="forbid": 未知キーは drift として reject (黙って捨てない)。
    with pytest.raises(ValidationError):
        CrawlCompletedDetail.model_validate({**GOLDEN_DETAIL, "race_id": "202605071205"})


@pytest.mark.parametrize(
    "missing", ["aspect", "stadium_tel_code", "race_holding_date", "race_number"]
)
def test_rejects_missing_field(missing: str) -> None:
    payload = {k: v for k, v in GOLDEN_DETAIL.items() if k != missing}
    with pytest.raises(ValidationError):
        CrawlCompletedDetail.model_validate(payload)
