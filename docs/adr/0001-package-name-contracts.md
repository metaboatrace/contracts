# ADR 0001: 共有契約パッケージを `metaboatrace.contracts` として独立リポに切る

- Status: Accepted
- Date: 2026-06-18
- 関連: metaboatrace/ml issue #14（投票指示契約を型パッケージとして ml/voting で共有する）、
  `metaboatrace.models`（対比するドメインエンティティ集約）、
  ml `metaboatrace/ml/prediction/decision_output.py`（producer の `to_contract_payload`）、
  voting `infrastructure/s3_bet_decision_repository.py`（consumer の `_BetPayload`）

## Context

ml（producer）→ voting（consumer）の Published Language（S3 上の bet decision JSON, schema v1）が、
**ml 側と voting 側で二重定義**されており、ドリフトし得る。現状は両リポの golden サンプル適合テストで
担保しているが、契約そのものを**単一の型**として共有したい（issue #14）。

契約パッケージに求める性質（issue #14 の方針）:

- **専用パッケージ**として共有する。`models`（ドメインエンティティ共有）に相乗りさせない。
- **pydantic のみ依存**。`models` のような重いドメイン型を引き込まない。
- **厚みは wire 構造の妥当性（well-formed v1）まで**。ドメイン意味論（race_id 年≥2016・100 円単位・
  betting policy）は各 Bounded Context に残す（ACL を崩さない）。
- consumer は **tag pin** して、契約変更を意図的な bump に強制する。
- producer の ml がオーナー。voting は契約パッケージのみに依存し、**ml リポ全体には依存しない**。

issue #14 は例として `metaboatrace.bet-decision-contract`（契約名で狭く）を挙げていたが、検討の結果
**2 点で方針を更新**した（下記 Decision）。

## Decision

### 1. 配置: ml/voting/models と並ぶ独立 git リポにする

各サービス（ml / voting / models）はそれぞれ独立した git リポであり、voting は現状 `metaboatrace.models`
にすら依存していない（自前のドメイン型を持つ）。契約を **独立リポ + 独立配布** にすることで:

- voting は契約パッケージ（pydantic のみ）を tag pin で取り込み、**ml リポ全体・重依存を引かない**。
- 「正本は ml」はチーム所有の意味として保ち、物理配置は独立させる（k8s が `k8s.io/api` を
  別 publish して diamond dependency を避けるのと同じ動機）。

ml リポのサブディレクトリを別配布する案も検討したが、voting の pin が ml のタグ名前空間に結合し、
ml が 2 配布を抱える複雑さが出るため却下した。

### 2. 命名: `bet-decision-contract` ではなく `metaboatrace.contracts` に広げる

1 契約 = 1 パッケージに割ると、今後パイプラインの他の契約（予測結果・決済結果など）を型化するたびに
パッケージが増え、凝集度が下がりすぎる。`bet-decision-contract` という名前は将来の他契約に対して**狭すぎ**、
`models` のように複数の契約を**一つのパッケージ**に収め、その役割（境界をまたぐ wire 契約 = Published
Language）を端的に示す名前にすべき、と判断した。

import は契約ごとのモジュールで分ける: `metaboatrace.contracts.bet_decision` → `BetDecisionV1`。

#### なぜ `contracts` か（命名候補の比較）

`models`（クリーンアーキテクチャのエンティティ）に対し、本パッケージは**境界をまたぐ wire 上のデータ型
（DTO）= Published Language** である。この性質を端的に示す名前として OSS の実例を調査した。

| 候補 | 代表 OSS / 規約 | 判定 |
|---|---|---|
| **`contracts`** | .NET / NServiceBus の "message **contracts** assembly"（所有サービスごとに 1 つ、NuGet で共有） | **採用** |
| `api` | Kubernetes `k8s.io/api`（machinery と分離し別 publish＝diamond dep 回避）、protobuf `*.api.v1` | 却下（下記） |
| `messages` | NServiceBus / MassTransit（`*.Messages.Commands/Events`） | 却下（下記） |
| `schemas` | LSST SQuaRE `shared/schemas/`、Kafka/Avro 界隈 | 却下（下記） |
| `-proto` / `idl` | protobuf / gRPC | 却下（我々は pydantic/JSON で protobuf ではない） |

採用理由（`contracts`）:

1. **チームの ubiquitous language と一致**。issue #14・`decision_output.py` のコメントとも一貫して
   「契約 / Published Language」と呼んでいる。命名が既存語彙に conform する。
2. **`models` との対比が最も明快**。models = ドメインエンティティ、contracts = 境界をまたぐ wire 上の合意。
   DDD でも Published Language の wire schema は内部ドメインモデルと**意図的に分離**するのが定石。
3. **将来スケールしても誤称にならない**。`messages` のように「message 限定」でも、`bet-decision` のように
   「1 契約限定」でもなく、`api` のように「callable な面」を過剰主張もしない。

## Consequences

- **良い点**: ml/voting の二重定義（golden 適合テストでの担保）を単一の型に集約できる。golden サンプルの
  正本を本パッケージに置き、ml/voting は「produce できる / consume できる」薄い適合テストだけ残せる。
  voting は pydantic のみの軽い依存で契約を取り込める。
- **バージョニングモデルの変更**: issue #14 が想定した「パッケージ version ↔ schema_version の 1:1」は、
  複数契約を 1 パッケージに収めることで成立しなくなる。代わりに **型名で版を持つ**（`BetDecisionV1`、
  破壊変更時は `V2` 併存）＋ wire は `schema_version` で自己記述 ＋ **パッケージ SemVer は配布単位**、
  という形に置き換える。tag pin による「意図的 bump に強制」は維持される。
- **コスト**: 新規 git リポ（CI / pre-commit / publish 経路の初期セットアップ）が要る。

## 却下した代替案

- **`models` に相乗り**: ドメインエンティティと wire DTO を混在させると層が崩れる（DDD の分離原則に反する）。
- **`metaboatrace.bet-decision-contract`（issue #14 の当初案）**: 将来の他契約に対して狭すぎ、凝集度が
  下がる。`models` 同様に複数契約を一つのパッケージに収める方が良い。
- **`api`**: k8s.io/api の「重依存を引かず別 publish」という動機は我々と同一だが、それは**命名ではなく
  分割方針**の話で、独立リポにすれば得られる。`api` は callable な RPC/HTTP 面を含意し、一方向の S3 文書
  受け渡しには過剰。
- **`messages`**: bet decision は文書/命令的で当てはまるが、将来 message でない契約（feature snapshot 等）を
  入れると `bet-decision` と同様の誤称化リスク。
- **`schemas`**: 既存コードベースで `schema` は既に複数概念に過負荷（`FeatureSchemaConfig` / model artifact
  schema / `schema_version`）。Published Language のニュアンスも薄く、`models` との境界がぼやける。
