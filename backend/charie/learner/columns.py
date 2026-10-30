"""Column type families, from the scanned data types (P07.7, P07.8).

Profiling and link-matching both ask the same question -- which kind of
value a column holds -- so the answer lives in one place.
"""

_INTEGER = ("smallint", "integer", "bigint", "smallserial", "serial", "bigserial")
_NUMERIC = ("numeric", "decimal", "real", "double precision", "money")
_TEXT = ("text",)
_BOOLEAN = ("boolean",)
_UUID = ("uuid",)
_DATE = ("date",)
_STAMP = ("timestamp",)
_TIME = ("time",)
_INTERVAL = ("interval",)
_JSON = ("json", "jsonb")
_XML = ("xml",)
_GEOMETRIC = ("point", "line", "lseg", "box", "path", "polygon", "circle", "geometry", "geography")


def _base(data_type: str) -> str:
    """`numeric(10,2)` becomes `numeric`; arrays stay marked."""
    return (data_type or "").strip().lower().split("(")[0].strip()


def family(data_type: str) -> str:
    """One value family: integer, numeric, text, boolean,
    uuid, date, time, json, xml, geometric or other."""
    base = _base(data_type)
    if base in _INTEGER:
        return "integer"
    if base in _NUMERIC or base.startswith("decimal"):
        return "numeric"
    if base in _TEXT or base.startswith("character"):
        return "text"
    if base in _BOOLEAN:
        return "boolean"
    if base in _UUID:
        return "uuid"
    if base in _DATE or base.startswith("timestamp"):
        return "date"
    if base in _TIME or base in _INTERVAL or base.endswith(" with time zone"):
        return "time"
    if base in _JSON:
        return "json"
    if base in _XML:
        return "xml"
    if base in _GEOMETRIC:
        return "geometric"
    return "other"
