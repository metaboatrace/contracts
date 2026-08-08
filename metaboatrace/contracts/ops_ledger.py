"""ops-ledger レコード契約 (voting / ml / infra → 突合バッチ, AWS DynamoDB) の wire 型.

レース単位ではない **日次の運用事実** を残す台帳。日次工程 (deposit・feature store の
materialize 等) の結末と、運用ノブ (SSM パラメータ) の変更観測を同じテーブルに積む。突合
バッチ (consumer) が「その日レース単位の記録が薄いのは、そもそも日次工程が失敗していた
からか」「歩留まりの段差はノブを触ったせいか」を後から説明できるようにするための記録。

``metaboatrace.contracts`` の責務どおり **wire 構造の妥当性 (well-formed) まで**を担い、
ドメイン意味論は各 Bounded Context に残す:

- ``date`` の暦日妥当性 (JST 暦日として実在するか) は各 BC のドメイン。
- ``entry_id`` の書式規約 (``job#`` / ``knob#`` の組み立て) は producer のドメイン。
- ``kind`` と ``outcome`` / ``value`` の相関 (``job`` なら ``outcome``、``knob`` なら
  ``value``) という状態機械もドメイン。

``outcome`` を ``JobOutcome`` 型にせず素の ``str`` にしているのは、この item が 2 種類
(``job`` / ``knob``) の合併で、``kind`` に依存して意味を持つフィールドだから。値の語彙は
``JobOutcome`` が所有し、producer はそのメンバの値を書く。

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


class OpsEntryKind(StrEnum):
    """ops-ledger の entry 種別 (``kind`` 属性が取る値).

    取りうる種別の閉包 (enum メンバの網羅) は契約が所有する。値が wire 表現で、``StrEnum``
    なので ``model_dump(mode="json")`` では素の文字列にシリアライズされる。
    """

    JOB = "job"
    """日次工程の結末 (deposit / feature_store_materialize 等)。"""

    KNOB = "knob"
    """運用ノブ (SSM パラメータ) の変更観測。"""


class JobOutcome(StrEnum):
    """日次工程の結末 (``kind == job`` の item の ``outcome`` に書かれる値の語彙).

    ``OpsLedgerRecord.outcome`` は ``kind`` 依存のフィールドなので wire 型は ``str`` だが、
    値の語彙はこの enum が所有する。producer はこのメンバの値を書く。
    """

    OK = "ok"
    """正常終了。"""

    FAILED = "failed"
    """異常終了。"""

    UNKNOWN = "unknown"
    """結末が確認できない (人間の確認が必要)。"""

    SKIPPED = "skipped"
    """kill switch / already-funded 等で何もしなかった (no-op)。"""


class OpsLedgerRecord(BaseModel):
    """運用台帳 (ops-ledger) の DynamoDB item 1 件の wire 表現.

    hash = ``date`` (S, JST 暦日 ``YYYY-MM-DD``) / range = ``entry_id`` (S)。

    ``entry_id`` の規約:

    - job:  ``"job#<job_name>"``  例 ``"job#deposit"`` / ``"job#feature_store_materialize"``
    - knob: ``"knob#<param_name>#<HHMMSS>"``
      例 ``"knob#/metaboatrace/production/voting/DRY_RUN#083012"``
      (同日に複数回変更されうるので時刻 (JST) まで含めて別 item として残す)
    """

    model_config = ConfigDict(extra="forbid")

    date: str
    """JST 暦日 ``YYYY-MM-DD``。partition key。暦日妥当性はドメインに残す。"""

    entry_id: str
    """entry の識別子。sort key。書式規約は producer のドメインに残す。"""

    kind: OpsEntryKind
    """entry 種別。enum の網羅は契約が所有 (未知値は reject)。"""

    outcome: str | None = None
    """``kind == job`` のときの結末 (``JobOutcome`` の値)。``knob`` では載らないため optional。"""

    value: str | None = None
    """``kind == knob`` のときの変更後の値 (SSM ``GetParameter`` で取得)。``job`` では載らない。"""

    detail: str | None = None
    """補足 (例外型名・変更理由等)。無ければ wire に出さない。"""

    recorded_at: AwareUtcDatetime
    """記録した時刻 (aware, wire は UTC)。"""
