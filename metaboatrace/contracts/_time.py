"""wire 上の instant 表現を型で強制する.

時刻の取り扱い標準 (handbook): instant は aware で扱い、wire の正準表現は **UTC**。
naive を reject し UTC へ正規化することで、「golden は JST のはずが実装は UTC を吐く」
といった表記ドリフトを型レベルで封じる (golden の round-trip だけでは検知できない)。

- 入力: aware 必須 (naive は ValidationError)。任意のオフセットを受け、UTC へ正規化する。
- 出力 (JSON): ISO 8601 の UTC (`...+00:00`)。python モードでは aware UTC の datetime のまま。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, PlainSerializer


def _to_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("instant は timezone-aware でなければならない (naive は不可)")
    return value.astimezone(UTC)


AwareUtcDatetime = Annotated[
    datetime,
    AfterValidator(_to_aware_utc),
    PlainSerializer(lambda value: value.isoformat(), return_type=str, when_used="json"),
]
