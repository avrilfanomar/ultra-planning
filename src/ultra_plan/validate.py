from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_DIR = Path(__file__).parent / "schema"
SCHEMA_FILES = ("skills", "tools", "permissions", "bundle")


@lru_cache(maxsize=1)
def _registry() -> Registry:
    resources = []
    for name in SCHEMA_FILES:
        data = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())
        resources.append((data["$id"], Resource(contents=data, specification=DRAFT202012)))
    return Registry().with_resources(resources)


@lru_cache(maxsize=1)
def _bundle_validator() -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / "bundle.schema.json").read_text())
    return Draft202012Validator(schema, registry=_registry())


def validate_bundle(bundle: dict[str, Any]) -> None:
    _bundle_validator().validate(bundle)
