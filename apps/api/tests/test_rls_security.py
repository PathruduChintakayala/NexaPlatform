from __future__ import annotations

from sqlalchemy import String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

import pytest

from app.platform.security.context import AuthContext
from app.platform.security.errors import AuthorizationError
from app.platform.security.rls import apply_rls_filter, validate_rls_write


class Base(DeclarativeBase):
    pass


class DemoScopedModel(Base):
    __tablename__ = "demo_scoped_model"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_code: Mapped[str] = mapped_column(String(32))
    region_code: Mapped[str] = mapped_column(String(32))


def test_apply_rls_filter_adds_entity_and_region_filters() -> None:
    ctx = AuthContext(user_id="u1", entity_scope=["LE1"], region_scope=["US"])
    stmt = apply_rls_filter(select(DemoScopedModel), "demo.resource", ctx)
    sql = str(stmt)

    assert "company_code" in sql
    assert "region_code" in sql


def test_validate_rls_write_blocks_out_of_scope_values() -> None:
    ctx = AuthContext(user_id="u2", entity_scope=["LE1"], region_scope=["US"])

    with pytest.raises(AuthorizationError):
        validate_rls_write("crm.contact", {"company_code": "LE2"}, ctx)

    with pytest.raises(AuthorizationError):
        validate_rls_write("crm.contact", {"region_code": "EU"}, ctx)


def test_validate_rls_write_admin_bypass() -> None:
    ctx = AuthContext(user_id="admin", entity_scope=["LE1"], region_scope=["US"], is_super_admin=True)

    validate_rls_write("crm.contact", {"company_code": "LE2", "region_code": "EU"}, ctx)
