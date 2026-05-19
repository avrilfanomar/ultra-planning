from __future__ import annotations

import pytest
from jsonschema import ValidationError

from tests.fixtures import malformed_bundle, valid_bundle
from ultra_plan.validate import (
    format_validation_error,
    validate_bundle,
    validate_bundle_friendly,
)


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


def test_format_validation_error_includes_pointer_and_value():
    b = valid_bundle()
    b["skills"][0]["origin"] = "not-a-valid-origin"
    try:
        validate_bundle(b)
    except ValidationError as e:
        formatted = format_validation_error(e)
    else:
        pytest.fail("expected ValidationError")
    assert "at /skills/0/origin" in formatted
    assert "not-a-valid-origin" in formatted


def test_format_validation_error_truncates_long_values():
    b = valid_bundle()
    b["skills"][0]["origin"] = "x" * 1000
    try:
        validate_bundle(b)
    except ValidationError as e:
        formatted = format_validation_error(e)
    else:
        pytest.fail("expected ValidationError")
    # The "offending value:" line is truncated to ~200 chars.
    value_line = next(
        line for line in formatted.splitlines() if line.lstrip().startswith("offending value:")
    )
    assert value_line.endswith("...")
    assert len(value_line) < 300


def test_validate_bundle_friendly_raises_runtime_error():
    b = valid_bundle()
    del b["plan_markdown"]
    with pytest.raises(RuntimeError) as exc_info:
        validate_bundle_friendly(b)
    msg = str(exc_info.value)
    assert "plan_markdown" in msg
    assert "at /" in msg
