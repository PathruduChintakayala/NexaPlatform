from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest

from app import audit
from app.crm.repositories import ContactRepository
from app.platform.security.context import AuthContext
from app.platform.security.errors import ForbiddenFieldError
from app.platform.security.fls import MASKED_FIELD_VALUE, apply_fls_read, validate_fls_write
from app.platform.security.policies import InMemoryPolicyBackend, set_policy_backend


@pytest.fixture(autouse=True)
def reset_policy_backend() -> Generator[None, None, None]:
    set_policy_backend(InMemoryPolicyBackend(default_allow=True))
    audit.audit_entries.clear()
    yield
    set_policy_backend(InMemoryPolicyBackend(default_allow=True))
    audit.audit_entries.clear()


def test_apply_fls_read_allow_mask_deny() -> None:
    set_policy_backend(InMemoryPolicyBackend(default_allow=False))
    ctx = AuthContext(
        user_id="user-1",
        tenant_id="tenant-1",
        permissions=[
            "crm.contact.field.read:first_name",
            "crm.contact.field.mask:email",
        ],
    )

    output = apply_fls_read(
        "crm.contact",
        {"first_name": "Ada", "email": "ada@example.com", "ssn": "123-45-6789"},
        ctx,
    )

    assert output == {"first_name": "Ada", "email": MASKED_FIELD_VALUE}
    assert any(entry["action"] == "fls.read" for entry in audit.audit_entries)


def test_validate_fls_write_denies_forbidden_fields() -> None:
    set_policy_backend(InMemoryPolicyBackend(default_allow=False))
    ctx = AuthContext(
        user_id="user-2",
        tenant_id="tenant-1",
        permissions=["crm.contact.field.edit:first_name"],
    )

    with pytest.raises(ForbiddenFieldError) as exc_info:
        validate_fls_write("crm.contact", {"first_name": "Grace", "title": "CTO"}, ctx)

    assert exc_info.value.fields == ["title"]
    assert any(entry["action"] == "fls.write" for entry in audit.audit_entries)


def test_contact_repository_end_to_end_enforcement() -> None:
    set_policy_backend(InMemoryPolicyBackend(default_allow=False))
    repo = ContactRepository()
    ctx = AuthContext(
        user_id="user-3",
        tenant_id="tenant-1",
        permissions=[
            "crm.contact.field.read:*",
            "crm.contact.field.mask:email",
            "crm.contact.field.edit:first_name",
            "crm.contact.field.edit:custom_fields.vip",
        ],
    )

    raw_record = {
        "id": str(uuid.uuid4()),
        "first_name": "Linus",
        "email": "linus@example.com",
        "department": "Engineering",
    }
    secured = repo.apply_read_security(raw_record, ctx)
    assert secured["first_name"] == "Linus"
    assert secured["email"] == MASKED_FIELD_VALUE
    assert secured["department"] == "Engineering"

    repo.validate_write_security({"first_name": "Linus", "custom_fields": {"vip": True}}, ctx)

    with pytest.raises(ForbiddenFieldError) as exc_info:
        repo.validate_write_security({"department": "Product"}, ctx)
    assert exc_info.value.fields == ["department"]
