"""bet decision 契約 (schema v1) の wire 型.

ml (producer) が S3 に払い出し、voting (consumer) が消費する Published Language。
``metaboatrace.contracts`` の責務どおり **wire 構造の妥当性 (well-formed v1) まで**を担い、
ドメイン意味論は各 Bounded Context に残す:

- ``race_id`` の妥当性 (12桁・年≥2016・電話投票コード/レース番号の範囲) はドメイン。
- ``finishing_order`` の艇番値域 (1-6)・重複なしはドメイン。
- ``amount_yen`` の 100 円単位・最小購入額などの betting policy はドメイン。
- ``bet_type`` の enum 化 (式別の網羅) はドメイン。

版管理: ``schema_version`` は ``Literal[1]`` で、v2 payload はこの v1 型では parse 不能に
なる (validation 時点の tripwire)。破壊的変更時はパッケージ major を上げ、この Literal を
``2`` にして clean cutover する (型名は ``BetDecision`` のまま据え置き)。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from metaboatrace.contracts._time import AwareUtcDatetime

# wire の schema_version が取る値。このパッケージの major version に対応する。
SCHEMA_VERSION = 1


class Bet(BaseModel):
    """1 つの買い目 (3連単 1 点) の wire 表現."""

    model_config = ConfigDict(extra="forbid")

    bet_type: str
    """式別。v1 は ``"trifecta"`` 固定。enum 化 (券種の網羅) は consumer のドメインに残す。"""

    finishing_order: tuple[int, int, int]
    """着順 (1着, 2着, 3着) の艇番。並びが着順を表す (index 0 = 1着)。
    艇番値域 (1-6)・重複なしの検証は consumer のドメインに残す。"""

    amount_yen: int = Field(gt=0)
    """購入金額 (円)。100 円単位などの betting policy は consumer のドメインに残す。"""

    odds_at_decision: float
    """購入を決定した時点の3連単オッズ。確定/払戻オッズとは別物 (締切前の暫定値)。"""


class BetDecision(BaseModel):
    """1 レース分の投票指示 (schema v1) の wire 表現."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    """契約バージョンの自己記述。``Literal`` 不一致は validation で reject される (tripwire)。"""

    race_id: str
    """レースID (12桁)。妥当性検証は consumer のドメインに残す。"""

    portfolio: str
    """この決定を出したポートフォリオの識別子 (例 ``"staging"``)。provenance。"""

    decided_at: AwareUtcDatetime
    """買い目を決定した時刻 (aware, wire は UTC)。``odds_at_decision`` はこの時点のオッズ。"""

    deadline_at: AwareUtcDatetime
    """レースの投票締切時刻 (tz-aware)。締切ガードの権威ソース。"""

    bets: list[Bet] = Field(min_length=1)
    """買い目のリスト。投票指示は最低 1 点を持つ (0 点なら producer は払い出さない)。"""
