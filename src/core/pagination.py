from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel


class CursorPage(BaseModel):
    items: list[Any]
    next_cursor: str | None = None
    prev_cursor: str | None = None
    total: int | None = None


def paginate(items: Sequence[Any], cursor: str | None = None, limit: int = 50) -> CursorPage:
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]
    item_list = list(items)
    last = item_list[-1] if item_list else None
    next_cursor = (last.get("id") if isinstance(last, dict) else getattr(last, "id", None)) if has_more else None if item_list else None
    return CursorPage(items=item_list, next_cursor=next_cursor, prev_cursor=cursor, total=None)
