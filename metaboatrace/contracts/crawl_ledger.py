"""crawl-ledger レコード契約 (crawlers → 突合バッチ / dashboard, AWS DynamoDB) の wire 型.

crawlers (producer) が 1 レース × 1 aspect ごとにクロールの結末を DynamoDB のクロール台帳へ
upsert し、突合バッチ (consumer) が「予想が起動しなかったレースは上流クロールの失敗なのか、
受け渡しの喪失なのか」を切り分けるための記録。``CrawlCompleted`` イベント (成功時のみ発火する
一過性のシグナル) と違い、**失敗・中止を含む全結末が残る**のがこの台帳の存在理由。

``metaboatrace.contracts`` の責務どおり **wire 構造の妥当性 (well-formed) まで**を担い、
ドメイン意味論は各 Bounded Context に残す:

- ``race_id`` の妥当性 (12桁・年≥2016・電話投票コード/レース番号の範囲) は各 BC のドメイン。
- ``held_on`` の暦日妥当性・``race_id`` 日付部との整合は各 BC のドメイン。
- ``aspect`` の enum 網羅は producer (crawlers) のドメイン (``crawl_completed`` と同方針)。
- ``outcome`` と ``error_class`` の相関 (``failed`` のときだけ載る) はドメイン。

版管理: この item は ``schema_version`` フィールドを **持たない** (実際に書かれている item に
無い値を契約で捏造しないため)。DynamoDB item には routing 層 (EventBridge の ``detail-type``
相当) も無いため、旧 schema を parse 時の tripwire で弾く術がない。破壊的変更時はパッケージ
major を上げ、producer/consumer を同時デプロイして clean cutover し、取りこぼしは
**配布バージョンの tag pin + 協調デプロイ**で防ぐ。consumer は tag pin して意図的な bump
のみ取り込む。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from metaboatrace.contracts._time import AwareUtcDatetime

# クロール台帳を当日分まとめて引くための GSI 名 (partition key = held_on)。主キーが
# race_id + aspect なので、日次の突合には別途この index が要る。実体は infra (Terraform) が
# 定義し、本契約が producer/consumer 間の合意として名前を固定する。
HELD_ON_INDEX = "held_on-index"


class CrawlOutcome(StrEnum):
    """クロールの結末 (crawl-ledger の ``outcome`` 属性が取る値).

    取りうる結末の閉包 (enum メンバの網羅) は契約が所有する。値が wire 表現で、``StrEnum``
    なので ``model_dump(mode="json")`` では素の文字列にシリアライズされる。
    """

    OK = "ok"
    """クロール成功 (``CrawlCompleted`` の発行と同時に記録する)。"""

    FAILED = "failed"
    """リトライ枯渇による最終失敗。``error_class`` に例外型名が載る。"""

    CANCELED = "canceled"
    """レース中止を確認した (per-race / 場単位とも)。"""

    REVOKED = "revoked"
    """場単位の中止に伴い当該レースのスケジュールを削除した (クロール自体を放棄)。"""


class CrawlLedgerRecord(BaseModel):
    """クロール台帳 (crawl-ledger) の DynamoDB item 1 件の wire 表現.

    hash = ``race_id`` (S) / range = ``aspect`` (S) で 1 レース × 1 aspect = 1 item を upsert
    (再実行で最新の結末に上書き)。GSI ``held_on-index`` (``HELD_ON_INDEX``) で当日一覧を引く。
    """

    model_config = ConfigDict(extra="forbid")

    race_id: str
    """レースID (12桁)。partition key。妥当性検証は各 BC のドメインに残す。"""

    aspect: str
    """クロール aspect (``races`` / ``before-information`` / ``trifecta-odds`` / ``result``)。
    sort key。enum 網羅は producer (crawlers) のドメインに残すため wire は素の ``str``。"""

    held_on: str
    """開催日 ``YYYY-MM-DD``。GSI ``held_on-index`` の partition key。暦日妥当性はドメイン。"""

    outcome: CrawlOutcome
    """クロールの結末。enum の網羅は契約が所有 (未知値は reject)。"""

    error_class: str | None = None
    """``outcome == failed`` のときの例外型名。正常時は載らないため optional。"""

    finished_at: AwareUtcDatetime
    """結末が確定した時刻 (aware, wire は UTC)。"""
