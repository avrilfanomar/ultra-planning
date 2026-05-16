from __future__ import annotations

import pytest
from jsonschema import ValidationError

from tests.fixtures import malformed_bundle, valid_bundle
from ultra_plan.validate import validate_bundle


def test_valid_bundle_passes():
    validate_bundle(valid_bundle())


def test_malformed_origin_rejected():
    with pytest.raises(ValidationError):
        validate_bundle(malformed_bundle())


def test_missing_required_field_rejected():
    b = valid_bundle()
    del b["plan_markdown"]
    with pytest.raises(ValidationError):
        validate_bundle(b)


def test_extra_field_rejected():
    b = valid_bundle()
    b["junk"] = 1
    with pytest.raises(ValidationError):
        validate_bundle(b)
