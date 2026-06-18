"""CrawlCompleted イベント契約 (crawlers → ml, AWS EventBridge) の wire 型.

crawlers (producer) が EventBridge カスタムバスへ ``PutEvents`` し、ml (consumer) の
予想 Lambda が subscribe する Published Language。EventBridge の routing 属性
(``source`` / ``detail-type``) と ``detail`` payload の wire 構造を固定する。

``metaboatrace.contracts`` の責務どおり **wire 構造の妥当性 (well-formed) まで**を担い、
ドメイン意味論は各 Bounded Context に残す:

- ``aspect`` の enum 網羅 (races / before-information / trifecta-odds / result) は producer のドメイン。
- ``stadium_tel_code`` の値域 (1-24)・``race_number`` の値域 (1-12)・``race_holding_date`` の
  暦日妥当性、およびこれらを連結した race_id の妥当性 (年≥2016 等) は consumer のドメイン。

版管理: この detail payload は ``schema_version`` フィールドを **持たない**。EventBridge の
``detail-type`` がイベント種別の識別子を兼ねるためで、破壊的変更時はパッケージ major を
上げ、``DETAIL_TYPE`` を別値 (例 ``"CrawlCompleted"`` → ``"CrawlCompletedV2"``) に切り替えて
clean cutover する。これにより EventBridge Rule レベルでも新旧を分離でき、旧 consumer は
新イベントを routing 段階で取りこぼす (sink せず黙殺) のではなく、そもそも受け取らない。
``SOURCE`` / ``DETAIL_TYPE`` は ``Literal`` 型の定数にして、両側のルーティング定数が
ドリフトしないよう型で固定する。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# EventBridge ``PutEvents`` の Source。crawlers が put し、ml consumer / infra の
# EventBridge Rule (event pattern の ``source``) がこの値で一致させる。
SOURCE: Literal["metaboatrace.crawlers"] = "metaboatrace.crawlers"

# EventBridge ``PutEvents`` の DetailType。クロール完了イベントの種別。
# Rule の ``detail-type`` でこの値に一致させる。破壊的変更時はこの値を bump する。
DETAIL_TYPE: Literal["CrawlCompleted"] = "CrawlCompleted"


class CrawlCompletedDetail(BaseModel):
    """``CrawlCompleted`` イベントの ``detail`` payload の wire 表現.

    EventBridge が Lambda へ届けるイベント外殻 (``id`` / ``time`` / ``account`` 等を含む)
    ではなく、producer が ``Detail`` に詰め consumer が ``event["detail"]`` で受け取る
    payload 本体を固定する。外殻のルーティング属性は ``SOURCE`` / ``DETAIL_TYPE`` を参照。
    """

    model_config = ConfigDict(extra="forbid")

    aspect: str
    """クロールした aspect (例 ``"trifecta-odds"``)。式別ならぬ aspect の enum 網羅は producer のドメインに残す。"""

    stadium_tel_code: int
    """電話投票コード (場識別)。値域 1-24 の検証は consumer のドメインに残す。"""

    race_holding_date: str
    """開催日 ``YYYYMMDD`` (例 ``"20260507"``)。暦日妥当性は consumer のドメインに残す。"""

    race_number: int
    """レース番号。値域 1-12 の検証は consumer のドメインに残す。"""
