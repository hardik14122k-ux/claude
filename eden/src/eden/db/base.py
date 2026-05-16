"""Declarative base. Control-plane models bind to the `eden_control` schema;
tenant-template models are schema-unqualified and resolve via the per-request
search_path set by the tenant router."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class ControlBase(DeclarativeBase):
    """Shared control plane. All tables live in schema `eden_control`."""

    metadata = MetaData(schema="eden_control", naming_convention=NAMING_CONVENTION)


class TenantBase(DeclarativeBase):
    """Per-client tenant template. No schema qualifier — the tenant router
    selects the active `client_<uuid>` schema via search_path per request."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
