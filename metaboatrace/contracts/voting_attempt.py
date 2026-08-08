"""voting-attempt-log レコード契約 (voting / infra recorder / 手動照合 → 突合バッチ,
AWS DynamoDB) の wire 型.

投票タスクの **全実行の結末** を無条件に append する観測用の台帳。voting アプリ自身が書く
結末に加え、アプリに到達すらしなかった実行 (EventBridge → RunTask の起動失敗、起動後の
タスク死亡) を infra の recorder が、``unknown`` の手動照合結果を運用スクリプトが同じテーブルへ
書く。突合バッチ (consumer) が「投票まで届いたか、届かなかったならどこで落ちたか」を
切り分けるための一次資料。

既存の voting-ledger (``metaboatrace.contracts.voting_ledger``) とは **別テーブル・別責務**:
あちらは冪等性制御の集約 (``attribute_not_exists`` 条件付き put の意味論を壊さないため、
CLAIM 前の記録を同居させない)。こちらは記録のための記録で、上書きせず append する。

``metaboatrace.contracts`` の責務どおり **wire 構造の妥当性 (well-formed) まで**を担い、
ドメイン意味論は各 Bounded Context に残す:

- ``race_id`` の妥当性 (12桁・年≥2016・電話投票コード/レース番号の範囲) は各 BC のドメイン。
- ``held_on`` の暦日妥当性・``race_id`` 日付部との整合は各 BC のドメイン。
- ``run_id`` の書式規約・``outcome`` と ``dry_run`` / ``detail`` の相関 (アプリ由来では
  ``dry_run`` が必ず載る等) は各 producer のドメイン。
- 「どの producer がどの ``outcome`` を書いてよいか」もドメイン (契約は値の閉包のみ所有)。

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

# 試行ログを当日分まとめて引くための GSI 名 (partition key = held_on)。主キーが
# race_id + run_id なので、日次の突合には別途この index が要る。実体は infra (Terraform) が
# 定義し、本契約が producer/consumer 間の合意として名前を固定する。
HELD_ON_INDEX = "held_on-index"


class VotingAttemptOutcome(StrEnum):
    """投票試行 1 回の結末 (voting-attempt-log の ``outcome`` 属性が取る値).

    取りうる結末の閉包 (enum メンバの網羅) は契約が所有する。値が wire 表現で、``StrEnum``
    なので ``model_dump(mode="json")`` では素の文字列にシリアライズされる。
    """

    # --- voting アプリ自身が書く (ユースケースの結末の wire 表現) ---

    PLACED = "placed"
    """投票確定。"""

    DRY_RUN = "dry_run"
    """dry-run で would-place のみ (副作用なし)。"""

    DUPLICATE = "duplicate"
    """既に claim / placed 済みで no-op。"""

    KILL_SWITCH = "kill_switch"
    """kill switch により何もせず中断。"""

    POLICY_BLOCKED = "policy_blocked"
    """上限・締切のガードで投票せず。"""

    BLOCKED_BY_INTERLOCK = "blocked_by_interlock"
    """deposit interlock により実投票を抑止。"""

    FAILED = "failed"
    """実コミット前と確証できる失敗 (金は動いていない)。"""

    UNKNOWN = "unknown"
    """投票が通ったか不明 (要手動照合)。"""

    # --- infra recorder が書く (アプリに到達しなかった実行) ---

    DISPATCH_FAILED = "dispatch_failed"
    """EventBridge → RunTask の起動失敗 (DLQ 由来)。タスクが立ち上がっていない。"""

    TASK_DIED = "task_died"
    """タスクは起動したがアプリ到達前に死亡 (ECS Task State Change 由来)。"""

    # --- 手動照合が書く ---

    RESOLVED_PLACED = "resolved_placed"
    """``unknown`` を照合した結果、実は投票されていた。"""

    RESOLVED_NOT_PLACED = "resolved_not_placed"
    """``unknown`` を照合した結果、投票されていなかった。"""


class VotingAttemptRecord(BaseModel):
    """投票試行ログ (voting-attempt-log) の DynamoDB item 1 件の wire 表現.

    hash = ``race_id`` (S) / range = ``run_id`` (S) の **append-only** な台帳 (同じ実行を
    上書きしない)。GSI ``held_on-index`` (``HELD_ON_INDEX``) で当日一覧を引く。

    既存 voting-ledger (``VotingLedgerRecord``) とは別テーブル・別責務: あちらは冪等性制御の
    集約、こちらは「投票タスクの全実行の結末」を無条件に記録する観測データ。
    """

    model_config = ConfigDict(extra="forbid")

    race_id: str
    """レースID (12桁)。partition key。妥当性検証は各 BC のドメインに残す。"""

    run_id: str
    """実行 ID。sort key。recorder 由来は ``"evt-<eventId>"``、手動照合は
    ``"manual-<YYYYMMDD-HHMMSS>"``。書式規約は producer のドメインに残す。"""

    held_on: str
    """開催日 ``YYYY-MM-DD``。GSI ``held_on-index`` の partition key。暦日妥当性はドメイン。"""

    outcome: VotingAttemptOutcome
    """試行の結末。enum の網羅は契約が所有 (未知値は reject)。"""

    dry_run: bool | None = None
    """実弾/紙の区別。アプリが書くときは必ず埋め、recorder 由来 (アプリ未到達) では載らない。"""

    detail: str | None = None
    """結末の理由 (violations 文字列・``stoppedReason``・例外 repr 等)。無ければ wire に出さない。"""

    attempted_at: AwareUtcDatetime
    """試行の結末を記録した時刻 (aware, wire は UTC)。"""
