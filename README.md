# metaboatrace.contracts

metaboatrace パイプラインの **Published Language（wire 契約）** を型として共有するパッケージ

- 境界（Bounded Context）をまたいで交換される wire 上のデータ型（DTO）を pydantic モデルとして
定義
- `metaboatrace.models`（クリーンアーキテクチャのドメインエンティティ）とは**層が違う別物**で、
こちらは「境界をまたぐ合意」そのものを表す

## 位置づけ

| パッケージ | 役割 |
|---|---|
| `metaboatrace.models` | 各サービスが共有するドメインエンティティ（不変条件・振る舞いを持つ） |
| **`metaboatrace.contracts`** | サービス間でやり取りされる **wire DTO（Published Language）** |

- contract の型（wire DTO）の正本は本パッケージにあり、producer / consumer の双方がこれに依存
- 命名・配置の根拠は [`docs/adr/0001-package-name-contracts.md`](docs/adr/0001-package-name-contracts.md) を参照

## 責務の境界（厚み）

- **担う**:
  - wire 構造の妥当性（well-formed なペイロードか）
- **担わない**:
  - ドメイン意味論（`race_id` の年≥2016・100 円単位・betting policy 等）
    - これらは各 Bounded Context のドメイン層に残し、契約型は ACL（`_to_domain`）で翻訳して使う

## バージョニング

- wire は `schema_version` フィールドで自己記述する（`Literal` で固定）
- 破壊的変更時は**パッケージ major を上げて `schema_version` を bump** し、producer / consumer を同時デプロイして **clean cutover** する
  - 型名は `BetDecision` のまま据え置き
    - `BetDecisionV1` / `BetDecisionV2` を併存させず、互換も持たせない
  - 旧 schema の payload は新 `Literal` で parse 不能になる
    - validation 時点の tripwire
- パッケージ SemVer は配布単位
  - consumer は **tag pin** して、意図的な bump のみ取り込む
  - 契約変更を暗黙に流入させない

## 開発

```sh
uv sync
uv run pytest
uv run pre-commit run --all-files
```
