from __future__ import annotations

import uuid
from collections.abc import Generator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crm.models import CRMAccount, CRMAccountLegalEntity, CRMContact
from app.crm.repositories import ContactRepository
from app.platform.security.context import AuthContext


def test_contact_repository_apply_scope_query_filters_by_entity_scope() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    le1 = uuid.uuid4()
    le2 = uuid.uuid4()

    with SessionLocal() as session:
        account1 = CRMAccount(name="A1", status="Active", primary_region_code="US")
        account2 = CRMAccount(name="A2", status="Active", primary_region_code="EU")
        session.add_all([account1, account2])
        session.flush()

        session.add_all(
            [
                CRMAccountLegalEntity(account_id=account1.id, legal_entity_id=le1, is_default=True),
                CRMAccountLegalEntity(account_id=account2.id, legal_entity_id=le2, is_default=True),
            ]
        )

        contact1 = CRMContact(account_id=account1.id, first_name="A", last_name="One", email="a@example.com")
        contact2 = CRMContact(account_id=account2.id, first_name="B", last_name="Two", email="b@example.com")
        session.add_all([contact1, contact2])
        session.commit()

        repo = ContactRepository()
        ctx = AuthContext(user_id="u1", entity_scope=[str(le1)], region_scope=["US"])

        scoped_query = repo.apply_scope_query(select(CRMContact), ctx)
        rows = session.scalars(scoped_query).all()

        assert len(rows) == 1
        assert rows[0].id == contact1.id
