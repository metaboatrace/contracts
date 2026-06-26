"""voting-ledger レコード契約 (voting → dashboard, AWS DynamoDB) の wire 型.

voting (producer) が投票の結末を DynamoDB の投票台帳へ 1 レース 1 item で書き、dashboard
(consumer) が「当日どのレースが投票確定/失敗/不明か・投票完了時刻」を Aurora を hot path で
叩かずに一覧するための read-model (infra ADR 0003)。本モジュールはその DynamoDB item の
wire 構造を Published Language として固定する。

``metaboatrace.contracts`` の責務どおり **wire 構造の妥当性 (well-formed) まで**を担い、
ドメイン意味論は各 Bounded Context に残す:

- ``race_id`` の妥当性 (12桁・年≥2016・電話投票コード/レース番号の範囲) は各 BC のドメイン。
- ``held_on`` の暦日妥当性・``race_id`` 日付部との整合は各 BC のドメイン。
- 「1レース＝最大1回の投票」や ``status`` の状態遷移 (claimed→placed/failed/unknown、終端
  からの再遷移禁止)、``placed`` には受付確証が1件以上必要、といった状態機械は producer
  (voting) のドメインに残す。
- ``amount`` の円単位や1日累計上限などの betting policy はドメイン。

本契約はあくまで **infra 境界の wire DTO**。voting はドメイン集約 ``VoteRecord`` を所有し、
契約型を直接ドメイン層へ持ち込まず ACL (永続化マッパー) で翻訳する。dashboard は read-only
consumer として wire を読む。

版管理: この item は ``schema_version`` フィールドを **持たない** (実 item に無い値を契約で
捏造しないため)。DynamoDB item には routing 層も無いため、破壊的変更はパッケージ major を
上げ producer/consumer を同時デプロイして clean cutover し、取りこぼしは **配布バージョンの
tag pin + 協調デプロイ**で防ぐ。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from metaboatrace.contracts._time import AwareUtcDatetime

# 投票台帳を当日分まとめて引くための GSI 名 (partition key = held_on)。consumer は
# この index で held_on (YYYY-MM-DD) を等値クエリし、race_id で各台帳を join する。
# 実体は infra (Terraform) が定義し、本契約が producer/consumer 間の合意として名前を固定する。
HELD_ON_INDEX = "held_on-index"


class VoteStatus(StrEnum):
    """投票の結末 (voting-ledger の ``status`` 属性が取る値).

    取りうる状態の閉包 (enum メンバの網羅) は契約が所有する。値が status の wire 表現で、
    ``StrEnum`` なので ``model_dump(mode="json")`` では素の文字列にシリアライズされる。状態
    遷移の規則 (終端からの再遷移禁止など) は producer のドメインに残す。
    """

    CLAIMED = "claimed"
    """投票を試みることを確保した (二重投票防止の占有)。まだ確定していない。"""

    PLACED = "placed"
    """投票確定 (テレボート受付確証あり)。``placed_at`` と ``confirmations`` が載る。"""

    FAILED = "failed"
    """投票が通っていないと確証できる失敗。``failure_reason`` が載る。"""

    UNKNOWN = "unknown"
    """通ったか不明 (人間の確認が必要)。安全側に倒し自動リトライしない。"""


class Confirmation(BaseModel):
    """テレボートが投票確定時に返す受付の証跡 (1件) の wire 表現."""

    model_config = ConfigDict(extra="forbid")

    acceptance_number: str
    """投票が受け付けられたことを示す受付番号。監査の証拠として不可逆に残す。"""

    accepted_at: AwareUtcDatetime
    """受付確証の時刻 (aware, wire は UTC)。"""

    raw: str | None = None
    """ベンダ生レスポンス (任意・監査用)。無ければ wire に出さない。"""


class VotingLedgerRecord(BaseModel):
    """投票台帳 (voting-ledger) の DynamoDB item 1 件の wire 表現.

    主キー ``race_id`` で 1 レース 1 item、GSI ``held_on-index`` (``HELD_ON_INDEX``) で当日
    一覧を引く。optional フィールドの有無は status と相関する (``placed`` で ``placed_at`` /
    ``confirmations``、``failed`` / ``unknown`` で ``failure_reason``) が、その状態機械は
    producer のドメインに残す。
    """

    model_config = ConfigDict(extra="forbid")

    race_id: str
    """レースID (12桁)。主キー。妥当性検証は各 BC のドメインに残す。"""

    held_on: str
    """開催日 ``YYYY-MM-DD``。GSI ``held_on-index`` の partition key。暦日妥当性はドメイン。"""

    status: VoteStatus
    """投票の結末。enum の網羅は契約が所有 (未知値は reject)。状態遷移規則はドメイン。"""

    claimed_at: AwareUtcDatetime
    """投票を確保した時刻 (aware, wire は UTC)。CLAIMED 以降は常に存在する。"""

    run_id: str
    """投票試行の実行 ID (provenance)。"""

    amount: int = Field(ge=0)
    """この投票指示の合計金額 (円)。1日累計上限などの policy はドメインに残す。"""

    placed_at: AwareUtcDatetime | None = None
    """投票完了時刻 (aware, wire は UTC)。``status == placed`` のときのみ載るため optional。"""

    confirmations: list[Confirmation] = Field(default_factory=list)
    """受付確証のリスト。``placed`` でのみ非空 (1件以上)。それ以外は空。"""

    failure_reason: str | None = None
    """``status`` が ``failed`` / ``unknown`` のときの理由。正常時は載らないため optional。"""
