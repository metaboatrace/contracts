# metaboatrace.contracts

metaboatrace パイプラインの **Published Language（wire 契約）** を型として共有するパッケージ。

境界（Bounded Context）をまたいで交換される wire 上のデータ型（DTO）を pydantic モデルとして
定義する。`metaboatrace.models`（クリーンアーキテクチャのドメインエンティティ）とは**層が違う別物**で、
こちらは「境界をまたぐ合意」そのものを表す。

## 位置づけ

| パッケージ | 役割 |
|---|---|
| `metaboatrace.models` | 各サービスが共有するドメインエンティティ（不変条件・振る舞いを持つ） |
| **`metaboatrace.contracts`** | サービス間でやり取りされる **wire DTO（Published Language）** |

producer（ml）が正本を所有し、consumer（voting 等）は本パッケージにのみ依存する
（ml リポ全体には依存しない）。命名の根拠は [`docs/adr/0001-package-name-contracts.md`](docs/adr/0001-package-name-contracts.md)。

## 責務の境界（厚み）

- **担う**: wire 構造の妥当性（well-formed なペイロードか）。
- **担わない**: ドメイン意味論（`race_id` の年≥2016・100 円単位・betting policy 等）。
  これらは各 Bounded Context のドメイン層に残し、契約型は ACL（`_to_domain`）で翻訳して使う。

## バージョニング

- 契約は**型名で版を持つ**（例 `BetDecisionV1`）。破壊的変更時は `BetDecisionV2` を**併存**追加し、
  移行期に両対応できるようにする。
- wire 自体も `schema_version` フィールドで自己記述する。
- パッケージ SemVer は配布単位。consumer は **tag pin** して、意図的な bump のみ取り込む
  （契約変更を暗黙に流入させない）。

## 開発

```sh
uv sync
uv run pytest
uv run pre-commit run --all-files
```

組織の Python 標準（uv / hatchling / Ruff / mypy strict / pre-commit）に準拠する。
