from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).parent / "schema"
SUBSCHEMAS = ("skills", "tools", "permissions")


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
