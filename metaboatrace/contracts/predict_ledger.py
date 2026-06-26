"""predict-ledger レコード契約 (ml → dashboard, AWS DynamoDB) の wire 型.

ml (producer) の predict Lambda が invocation ごとに DynamoDB の予想台帳へ 1 レース 1 item を
upsert し、dashboard (consumer) が「正常/異常を問わず当日の全レースの結末」を Aurora を
hot path で叩かずに一覧するための read-model (infra ADR 0003)。本モジュールはその
DynamoDB item の wire 構造を Published Language として固定する。

``metaboatrace.contracts`` の責務どおり **wire 構造の妥当性 (well-formed) まで**を担い、
ドメイン意味論は各 Bounded Context に残す:

- ``race_id`` の妥当性 (12桁・年≥2016・電話投票コード/レース番号の範囲) は各 BC のドメイン。
- ``held_on`` の暦日妥当性・``race_id`` 日付部との整合は各 BC のドメイン。
- ``outcome`` と ``n_bets`` の相関 (ok_bets⇔n_bets>0 / ok_nobets⇔n_bets=0)、``error`` の
  ときだけ ``error_class`` が載り ``decided_at`` が欠けうる、といった状態機械はドメイン。
- ``total_amount`` の 100 円単位などの betting policy はドメイン。

版管理: この item は bet decision (schema v1) のような ``schema_version`` フィールドを
**持たない** (実際に書かれている item に無い値を契約で捏造しないため)。DynamoDB item には
routing 層 (EventBridge の ``detail-type`` 相当) も無いため、旧 schema を parse 時の tripwire で
弾く術がない。破壊的変更時はパッケージ major を上げ、producer/consumer を同時デプロイして
clean cutover し、取りこぼしは **配布バージョンの tag pin + 協調デプロイ**で防ぐ。consumer は
tag pin して意図的な bump のみ取り込む。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from metaboatrace.contracts._time import AwareUtcDatetime

# 予想台帳を当日分まとめて引くための GSI 名 (partition key = held_on)。consumer は
# この index で held_on (YYYY-MM-DD) を等値クエリし、race_id で各台帳を join する。
# 実体は infra (Terraform) が定義し、本契約が producer/consumer 間の合意として名前を固定する。
HELD_ON_INDEX = "held_on-index"


class PredictOutcome(StrEnum):
    """予想の結末 (predict-ledger の ``outcome`` 属性が取る値).

    取りうる結末の閉包 (enum メンバの網羅) は契約が所有する。値が outcome の wire 表現で、
    ``StrEnum`` なので ``model_dump(mode="json")`` では素の文字列にシリアライズされる。
    """

    OK_BETS = "ok_bets"
    """正常終了・買い目あり (n_bets>0)。S3 に bet decision 契約が払い出される。"""

    OK_NOBETS = "ok_nobets"
    """正常終了・買い目なし (n_bets=0)。購入対象なし。"""

    ERROR = "error"
    """異常終了 (例外)。``error_class`` に例外型名が載る。"""


class PredictLedgerRecord(BaseModel):
    """予想台帳 (predict-ledger) の DynamoDB item 1 件の wire 表現.

    主キー ``race_id`` で 1 レース 1 item を upsert (再実行で最新の結末に上書き)、GSI
    ``held_on-index`` (``HELD_ON_INDEX``) で当日一覧を引く。optional フィールドの有無は
    outcome と相関する (``error`` 以外では ``error_class`` を持たず、決定前に失敗した
    ``error`` では ``decided_at`` を持たない) が、その状態機械はドメインに残す。
    """

    model_config = ConfigDict(extra="forbid")

    race_id: str
    """レースID (12桁)。主キー。妥当性検証は各 BC のドメインに残す。"""

    held_on: str
    """開催日 ``YYYY-MM-DD``。GSI ``held_on-index`` の partition key。暦日妥当性はドメイン。"""

    outcome: PredictOutcome
    """予想の結末。enum の網羅は契約が所有 (未知値は reject)。"""

    n_bets: int = Field(ge=0)
    """買い目点数。outcome との相関 (ok_bets⇔>0) はドメインに残す。"""

    total_amount: int = Field(ge=0)
    """買い目の合計購入金額 (円)。100 円単位などの betting policy はドメインに残す。"""

    model_version: str
    """この決定を出したポートフォリオ識別子 (例 ``"staging"``)。provenance。

    値は実際にはポートフォリオ識別子 (``PORTFOLIO_DIR.name``) で、bet decision 契約の
    ``portfolio`` と同義。フィールド名 ``model_version`` は既存 item に合わせた素直な抽出で、
    ``portfolio`` への改名は破壊的変更 (major bump + clean cutover) として別途行う。
    """

    decided_at: AwareUtcDatetime | None = None
    """予想完了時刻 (aware, wire は UTC)。決定前に失敗した ``error`` では欠落しうるため optional。"""

    error_class: str | None = None
    """``outcome == error`` のときの例外型名。正常時は載らないため optional。"""
