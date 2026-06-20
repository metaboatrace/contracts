# ADR 0001: 共有契約パッケージを `metaboatrace.contracts` として独立リポに切る

- Status: Accepted
- Date: 2026-06-18
- 関連: `metaboatrace.models`（対比するドメインエンティティ集約）

## Context

- ml（producer）→ voting（consumer）の Published Language（S3 上の bet decision JSON, schema v1）が **ml 側と voting 側で二重定義** されており、ドリフトし得る
  - 契約を**単一の型**として共有したい

共有方式に求める性質:

- **専用パッケージ**として共有する
  - `models`（ドメインエンティティ共有）に相乗りさせない
- **pydantic のみ依存**
  - `models` のような重いドメイン型を引き込まない
- **厚みは wire 構造の妥当性（well-formed v1）まで**
  - ドメイン意味論（race_id 年≥2016・100 円単位・betting policy）は各 Bounded Context に残す
    - ACL を崩さない
- consumer は **tag pin** して、契約変更を意図的な bump に強制する

## Decision

### 1. 配置: ml/voting/models と並ぶ独立 git リポにする

- 各サービス（ml / voting / models）はそれぞれ独立した git リポであり、voting は現状 `metaboatrace.models`
にすら依存していない（自前のドメイン型を持つ）
  - 契約を **独立リポ + 独立配布** にすることで、voting は 契約パッケージ（pydantic のみ）を tag pin で取り込み、**ml リポ全体・重依存を引かない**

- ml リポのサブディレクトリを別配布する案も検討したが、voting の pin が ml のタグ名前空間に結合し、 ml が 2 配布を抱える複雑さが出るため却下

### 2. 命名: `metaboatrace.contracts`（1 契約 1 パッケージにしない）

- 1 契約 = 1 パッケージに割ると、今後パイプラインの他の契約（予測結果・決済結果など）を型化するたびにパッケージが増え、凝集度が下がりすぎる
  - `models` のように複数の契約を**一つのパッケージ**に収め、その役割（境界をまたぐ wire 契約 = Published Language）を端的に示す名前にする
- import は契約ごとのモジュールで分ける: `metaboatrace.contracts.bet_decision` → `BetDecision`

#### なぜ `contracts` か（命名候補の比較）

`models`（クリーンアーキテクチャのエンティティ）に対し、本パッケージは**境界をまたぐ wire 上のデータ型
（DTO）= Published Language** である。この性質を端的に示す名前として OSS の実例を調査した。

| 候補 | 代表 OSS / 規約 | 判定 |
|---|---|---|
| **`contracts`** | .NET / NServiceBus の "message **contracts** assembly"（所有サービスごとに 1 つ、NuGet で共有） | **採用** |
| `api` | Kubernetes `k8s.io/api`（machinery と分離し別 publish＝diamond dep 回避）、protobuf `*.api.v1` | 却下 |
| `messages` | NServiceBus / MassTransit（`*.Messages.Commands/Events`） | 却下 |
| `schemas` | LSST SQuaRE `shared/schemas/`、Kafka/Avro 界隈 | 却下 |
| `-proto` / `idl` | protobuf / gRPC | 却下（我々は pydantic/JSON で protobuf ではない） |

採用理由（`contracts`）:
- チームの ubiquitous language（「契約 / Published Language」）と一致する
- `models` （ドメインエンティティ）との対比が最も明快
- 将来契約が増えても誤称にならない

## バージョニング

- 各契約の wire は `schema_version` フィールドで自己記述する（`Literal` で固定）
- 破壊的変更時は**型名を据え置いたまま**（`BetDecision` のまま）パッケージ major を上げて `schema_version` を bump し、producer / consumer を同時デプロイして **clean cutover** する
  - `V1`/`V2` を併存させて両対応はしない
- 旧 schema の payload は新 `Literal` で parse 不能になり、validation 時点の tripwire になる
  - パッケージ SemVer は配布単位で、consumer は tag pin して意図的な bump のみ取り込む

## 却下した代替案

- **`models` に相乗り**:
  - ドメインエンティティと wire DTO を混在させると層が崩れる（DDD の分離原則に反する）
- **`metaboatrace.bet-decision-contract`（1 契約 1 パッケージ）**:
  - 将来の他契約に対して狭すぎ、凝集度が下がる
  - `models` 同様に複数契約を一つのパッケージに収める方が良い
- **`api`**:
  - callable な RPC/HTTP 面を含意するが、本パッケージはデータ payload（DTO）であって呼び出し可能な面を持たないため不適切
  - 「重依存を引かず別 publish」という k8s.io/api の動機は命名ではなく分割方針の話で、独立リポにすれば得られる
- **`messages`**:
  - 将来 message でない契約（feature snapshot 等）を入れると `bet-decision` と同様の誤称化リスク
- **`schemas`**:
  - 既存コードベースで `schema` は既に過負荷（`FeatureSchemaConfig` / model artifact schema / `schema_version`）
  - Published Language のニュアンスも薄く、`models` との境界がぼやける
