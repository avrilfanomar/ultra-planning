from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

SCHEMA_DIR = Path(__file__).parent / "schema"
SUBSCHEMAS = ("skills", "tools", "permissions")

_VALUE_REPR_LIMIT = 200


@lru_cache(maxsize=1)
def _bundle_validator() -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / "bundle.schema.json").read_text())
    subs = {}
    for name in SUBSCHEMAS:
        data = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())
        subs[data["$id"]] = data
    for key, prop in schema.get("properties", {}).items():
        ref = prop.get("$ref") if isinstance(prop, dict) else None
        if ref in subs:
            schema["properties"][key] = subs[ref]
    return Draft202012Validator(schema)


def validate_bundle(bundle: dict[str, Any]) -> None:
    _bundle_validator().validate(bundle)


def format_validation_error(exc: ValidationError) -> str:
    """Render a ValidationError into a multi-line, JSON-pointer-aware message.

    Format:
        <message>
          at /<json/pointer>
          offending value: <repr-truncated>
    """
    pointer = "/" + "/".join(str(p) for p in exc.absolute_path) if exc.absolute_path else "/"
    try:
        rendered = repr(exc.instance)
    except Exception:
        rendered = "<unrepresentable>"
    if len(rendered) > _VALUE_REPR_LIMIT:
        rendered = rendered[:_VALUE_REPR_LIMIT] + "..."
    return f"{exc.message}\n  at {pointer}\n  offending value: {rendered}"


def validate_bundle_friendly(bundle: dict[str, Any]) -> None:
    """Validate; on failure, raise RuntimeError with a formatted message."""
    try:
        validate_bundle(bundle)
    except ValidationError as e:
        raise RuntimeError(format_validation_error(e)) from e
