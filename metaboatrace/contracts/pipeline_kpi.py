"""パイプライン歩留まり KPI 契約 (突合バッチ → dashboard, AWS DynamoDB) の wire 型.

自動投票パイプライン (crawlers → ml → voting) の歩留まりを算出するための語彙。T+1 の突合
バッチ (producer) が当日の全レースを **ちょうど 1 つの終端分類** に確定させて kpi-ledger へ
書き、dashboard (consumer) が日次の歩留まりを読む。分類の語彙を複数サービス
(crawlers / ml / voting / infra recorder / 突合バッチ / dashboard) が共有するため、
終端分類 enum と KPI item の wire 構造を Published Language として本モジュールが固定する。

``metaboatrace.contracts`` の責務どおり **wire 構造の妥当性 (well-formed) まで**を担い、
ドメイン意味論は各 Bounded Context に残す:

- ``race_id`` の妥当性 (12桁・年≥2016・電話投票コード/レース番号の範囲) は各 BC のドメイン。
- ``held_on`` の暦日妥当性・``race_id`` 日付部との整合は各 BC のドメイン。
- 「どの台帳をどう突き合わせるとどの分類になるか」という分類規則そのもの、および
  ``counts`` が enum を網羅すること・``yield_rate`` が ``counts`` と整合することは
  producer (突合バッチ) のドメインに残す。
- ``dry_run`` と分類の相関 (GOOD_PLACED は実弾・GOOD_WOULD_PLACE は紙) もドメイン。

契約が所有するのは **分類の閉包 (enum メンバ) と、それを歩留まりの分子・分母へ写す集合定義**
(``GOOD_CATEGORIES`` / ``EXCLUDED_CATEGORIES``)。突合バッチと dashboard が同じ計算式に
conform するよう、この 2 集合を契約側に置く。

版管理: この item は ``schema_version`` フィールドを **持たない** (実際に書かれている item に
無い値を契約で捏造しないため)。DynamoDB item には routing 層 (EventBridge の ``detail-type``
相当) も無いため、旧 schema を parse 時の tripwire で弾く術がない。破壊的変更時はパッケージ
major を上げ、producer/consumer を同時デプロイして clean cutover し、取りこぼしは
**配布バージョンの tag pin + 協調デプロイ**で防ぐ。consumer は tag pin して意図的な bump
のみ取り込む。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from metaboatrace.contracts._time import AwareUtcDatetime

# 日次サマリ item の range key 値。レース item (range = race_id) と同一 partition に同居する
# ため、数字始まりの race_id と衝突しない先頭アンダースコアを使う。
SUMMARY_SORT_KEY = "_SUMMARY"


class RaceKpiCategory(StrEnum):
    """レース 1 件の終端分類 (kpi-ledger の ``category`` 属性が取る値).

    全レースがちょうど 1 つ持つ結末カテゴリで、取りうる分類の閉包 (enum メンバの網羅) は
    契約が所有する。値が wire 表現で、``StrEnum`` なので ``model_dump(mode="json")`` では
    素の文字列にシリアライズされる。どの台帳の状態がどの分類に落ちるかという判定規則は
    producer (突合バッチ) のドメインに残す。
    """

    # --- 良品 (歩留まりの分子) ---

    GOOD_PLACED = "good_placed"
    """予想 → 買い目 → 投票成功。実弾で完走した。"""

    GOOD_WOULD_PLACE = "good_would_place"
    """dry-run で完走した (would-place まで到達)。紙の上では投票まで通っている。"""

    GOOD_NOBETS = "good_nobets"
    """予想は正常完了し、買い目が出なかった。購入対象なしで正常。"""

    # --- 分母除外 ---

    CANCELED = "canceled"
    """レース中止・順延。そもそも開催されなかったので分母に数えない。"""

    SUPPRESSED_KILL_SWITCH = "suppressed_kill_switch"
    """kill switch による意図的停止。運用判断なのでロスではない。"""

    SUPPRESSED_INTERLOCK = "suppressed_interlock"
    """deposit interlock による抑止。資金面の安全機構が働いた意図的停止。"""

    # --- ロス (分母に残る) ---

    LOSS_CRAWL = "loss_crawl"
    """上流クロールの失敗 (odds 等)。予想の入力が揃わなかった。"""

    LOSS_DELIVERY_ML = "loss_delivery_ml"
    """crawlers → ml のイベント/invoke 喪失。予想が起動しなかった。"""

    LOSS_PREDICT = "loss_predict"
    """予想の異常終了。"""

    LOSS_DELIVERY_VOTING = "loss_delivery_voting"
    """ml → voting の受け渡し喪失 (S3 upload 失敗 / RunTask 不発 / タスク死亡)。"""

    LOSS_DEADLINE = "loss_deadline"
    """締切ガードで投票を見送った。"""

    LOSS_VOTE_FAILED = "loss_vote_failed"
    """投票の実コミット前失敗。投票は通っていないと確証できる。"""

    # --- 別枠 ---

    UNKNOWN_VOTE = "unknown_vote"
    """投票が通ったか不明 (要手動照合)。歩留まりと別建ての最上位安全 KPI。"""

    MISSING = "missing"
    """どの台帳にも記録が無い。集計品質の異常で、> 0 ならアラート。"""


GOOD_CATEGORIES: frozenset[RaceKpiCategory] = frozenset(
    {
        RaceKpiCategory.GOOD_PLACED,
        RaceKpiCategory.GOOD_WOULD_PLACE,
        RaceKpiCategory.GOOD_NOBETS,
    }
)
"""歩留まりの **分子** に数える分類 (良品)。"""

EXCLUDED_CATEGORIES: frozenset[RaceKpiCategory] = frozenset(
    {
        RaceKpiCategory.CANCELED,
        RaceKpiCategory.SUPPRESSED_KILL_SWITCH,
        RaceKpiCategory.SUPPRESSED_INTERLOCK,
    }
)
"""歩留まりの **分母から除外** する分類 (中止・意図的停止)。

これに該当しない分類 (良品・ロス・``UNKNOWN_VOTE`` / ``MISSING``) はすべて分母に残る::

    base       = 期待レース数 − EXCLUDED_CATEGORIES の件数
    歩留まり   = GOOD_CATEGORIES の件数 / base        # base が 0 のときは 1.0
    UNKNOWN 率 = UNKNOWN_VOTE の件数 / base
"""


class RaceKpiRecord(BaseModel):
    """KPI 台帳 (kpi-ledger) のレース item 1 件の wire 表現.

    hash = ``held_on`` (S) / range = ``race_id`` (S)。hash が ``held_on`` なので当日一覧は
    素の query で引け、GSI は持たない。同一 partition には日次サマリ item
    (range = ``SUMMARY_SORT_KEY``) が同居する。
    """

    model_config = ConfigDict(extra="forbid")

    held_on: str
    """開催日 ``YYYY-MM-DD`` (JST 暦日)。partition key。暦日妥当性はドメインに残す。"""

    race_id: str
    """レースID (12桁)。sort key。妥当性検証は各 BC のドメインに残す。"""

    category: RaceKpiCategory
    """終端分類。enum の網羅は契約が所有 (未知値は reject)。判定規則はドメイン。"""

    dry_run: bool | None = None
    """voting まで到達したレースのみ載る、良品の実弾/紙の区別。未到達では欠落するため optional。"""

    detail: str | None = None
    """分類根拠の短文 (例外クラス名・``stoppedReason`` 等)。無ければ wire に出さない。"""

    source: str
    """分類の根拠にした台帳 (``"attempt-log"`` / ``"predict-ledger"`` / ``"crawl-ledger"`` /
    ``"reconciliation"``)。provenance。値の閉包は producer のドメインに残す。"""

    finalized_at: AwareUtcDatetime
    """突合バッチが分類を確定した時刻 (aware, wire は UTC)。"""


class DailyKpiSummary(BaseModel):
    """KPI 台帳 (kpi-ledger) の日次サマリ item 1 件の wire 表現.

    hash = ``held_on`` / range = ``SUMMARY_SORT_KEY``。レース item と同一 partition に同居し、
    dashboard は当日 1 件の GetItem でサマリだけを読める。``counts`` と ``yield_rate`` /
    ``unknown_rate`` の整合、および ``counts`` が enum を網羅することは producer のドメイン。
    """

    model_config = ConfigDict(extra="forbid")

    held_on: str
    """開催日 ``YYYY-MM-DD`` (JST 暦日)。partition key。"""

    expected_races: int = Field(ge=0)
    """その日に期待されたレース数 (分母の元)。"""

    counts: dict[str, Annotated[int, Field(ge=0)]]
    """``RaceKpiCategory`` の値 → 件数。enum の網羅は producer が保証する (契約は強制しない)。"""

    yield_rate: float = Field(ge=0.0, le=1.0)
    """歩留まり (0.0–1.0)。分母が 0 のときは 1.0。"""

    unknown_rate: float = Field(ge=0.0, le=1.0)
    """UNKNOWN 率 (0.0–1.0)。歩留まりと別建ての最上位安全 KPI。"""

    finalized_at: AwareUtcDatetime
    """突合バッチが日次集計を確定した時刻 (aware, wire は UTC)。"""
