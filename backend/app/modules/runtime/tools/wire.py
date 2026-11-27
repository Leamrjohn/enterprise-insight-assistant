"""M3: values JSON loses on the way to and from the tool service.

SQL rows hold Decimal, date and datetime values inside tuples; plain JSON turns
them into strings and lists.  encode() marks each one with its type, and
decode() on the other side rebuilds exactly what the tool returned, so nothing
downstream can tell the result crossed a process boundary.
"""

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

TYPE_KEY = "__type__"

_PARSERS: dict[str, Callable[[str], Any]] = {
    "decimal": Decimal,
    "date": date.fromisoformat,
    "datetime": datetime.fromisoformat,
}


def encode(value: Any) -> Any:
    """A JSON-safe copy of value; Decimal, date, datetime and tuple carry TYPE_KEY.

    {"__type__": "decimal", "value": "12.50"}    Decimal("12.50")
    {"__type__": "date", "value": "2025-08-01"}  date(2025, 8, 1)
    {"__type__": "datetime", "value": "..."}     datetime, via isoformat()
    {"__type__": "tuple", "items": [...]}        a tuple, items encoded too
    Lists and dicts are copied with their items encoded; str, int, float, bool
    and None stay as they are.  A dict that already has TYPE_KEY would come back
    as something else, so it is refused with ValueError.
    """
    if isinstance(value, Decimal):
        # str, not float: Decimal("0.10") must not come back as 0.1.
        return {TYPE_KEY: "decimal", "value": str(value)}
    # datetime before date: a datetime is a date too.
    if isinstance(value, datetime):
        return {TYPE_KEY: "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {TYPE_KEY: "date", "value": value.isoformat()}
    if isinstance(value, tuple):
        return {TYPE_KEY: "tuple", "items": [encode(item) for item in value]}
    if isinstance(value, list):
        return [encode(item) for item in value]
    if isinstance(value, dict):
        if TYPE_KEY in value:
            raise ValueError(f"{TYPE_KEY} is reserved for marked values")
        return {key: encode(item) for key, item in value.items()}
    return value


def decode(value: Any) -> Any:
    """Undo encode(): rebuild every marked value; anything else stays as it is.

    An unknown marker raises KeyError, which the client reports as malformed.
    """
    if isinstance(value, list):
        return [decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    marker = value.get(TYPE_KEY)
    if marker is None:
        return {key: decode(item) for key, item in value.items()}
    if marker == "tuple":
        return tuple(decode(item) for item in value["items"])
    return _PARSERS[marker](value["value"])
