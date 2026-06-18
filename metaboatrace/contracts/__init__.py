"""metaboatrace の Published Language (wire 契約) を集約するパッケージ.

このパッケージは、metaboatrace パイプラインの境界 (Bounded Context) をまたいで
交換される **wire 上のデータ型 (DTO)** を提供する。各サービスの内部ドメイン
エンティティ (``metaboatrace.models`` / 各リポの domain 層) とは層が異なり、
**境界をまたぐ「合意」= DDD の Published Language** を表現する。

責務の境界 (厚み):
    wire 構造の妥当性 (well-formed) までを担う。ドメイン意味論 (race_id の年≥2016、
    100 円単位、betting policy 等) は各 Bounded Context のドメイン層に残す。

バージョニング:
    契約は型名で版を持つ (例 ``BetDecisionV1``)。破壊的変更時は ``V2`` を併存追加し、
    移行期に両対応できるようにする。wire 自体も ``schema_version`` フィールドで自己記述する。
    パッケージ SemVer は配布単位で、consumer は tag pin して意図的な bump のみ取り込む。

所有:
    producer である ml チームが正本を所有する。consumer (voting 等) は本パッケージにのみ
    依存し、ml リポ全体には依存しない。

詳細な命名の根拠は ``docs/adr/0001-package-name-contracts.md`` を参照。
"""

from __future__ import annotations

__all__: list[str] = []
