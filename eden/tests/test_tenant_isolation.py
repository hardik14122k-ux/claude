"""The schema-identifier fail-safe (spec #3). Pure, no DB."""

import pytest

from eden.config import get_settings
from eden.db.session import assert_valid_tenant_schema


def test_generated_schema_name_is_accepted():
    settings = get_settings()
    name = settings.tenant_schema_name("0b3c8e7a-9f4d-4c1b-8a2e-1d2c3b4a5f60")
    assert name == "client_0b3c8e7a9f4d4c1b8a2e1d2c3b4a5f60"
    assert assert_valid_tenant_schema(name) == name


@pytest.mark.parametrize(
    "evil",
    [
        "client_x; DROP SCHEMA eden_control CASCADE; --",
        "eden_control",
        "public",
        "client_",
        "client_NOTHEX",
        'client_"; --',
        "",
    ],
)
def test_unsafe_identifiers_are_refused(evil):
    with pytest.raises(ValueError):
        assert_valid_tenant_schema(evil)
