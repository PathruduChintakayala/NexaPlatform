from __future__ import annotations

import csv
import io
import json
import uuid
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app import files_stub
from app.crm.models import CRMAccount, CRMAccountLegalEntity, CRMContact, CRMJob, CRMJobArtifact
from app.crm.schemas import AccountCreate, AccountUpdate, ContactCreate


def _is_read_all(actor_user: Any) -> bool:
    return "crm.accounts.read_all" in actor_user.permissions


def _visible_account_by_name(session: Session, actor_user: Any, name: str) -> CRMAccount | None:
    stmt: Select[tuple[CRMAccount]] = (
        select(CRMAccount)
        .join(CRMAccountLegalEntity, CRMAccountLegalEntity.account_id == CRMAccount.id)
        .where(and_(CRMAccount.deleted_at.is_(None), CRMAccount.name == name))
        .options(selectinload(CRMAccount.legal_entities))
        .distinct()
    )
    if not _is_read_all(actor_user):
        allowed = set(actor_user.allowed_legal_entity_ids)
        if not allowed:
            return None
        stmt = stmt.where(CRMAccountLegalEntity.legal_entity_id.in_(allowed))

    rows = session.scalars(stmt).all()
    if not rows:
        return None
    if len(rows) > 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="multiple accounts matched by name")
    return rows[0]


def _parse_bool(raw: str | None) -> bool:
    if raw is None:
        return False
    value = str(raw).strip().lower()
    return value in {"1", "true", "yes", "y"}


def _parse_uuid(raw: str | None) -> uuid.UUID | None:
    if raw is None or str(raw).strip() == "":
        return None
    return uuid.UUID(str(raw).strip())


def _parse_legal_entity_ids(raw: str | None) -> list[uuid.UUID]:
    if raw is None or str(raw).strip() == "":
        return []
    normalized = str(raw).replace(";", ",").replace("|", ",")
    values = [item.strip() for item in normalized.split(",") if item.strip()]
    return [uuid.UUID(item) for item in values]


def _row_error(row_number: int, code: str, message: str, field: str, raw_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_number": row_number,
        "error_code": code,
        "message": message,
        "field": field,
        "raw_row_json": json.dumps(raw_row),
    }


def _save_error_report(session: Session, job: CRMJob, errors: list[dict[str, Any]]) -> uuid.UUID | None:
    if not errors:
        return None
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["row_number", "error_code", "message", "field", "raw_row_json"])
    writer.writeheader()
    for error in errors:
        writer.writerow(error)
    payload = output.getvalue().encode("utf-8")
    file_id = files_stub.store_bytes(payload, f"crm_job_{job.id}_errors.csv", "text/csv")
    session.add(CRMJobArtifact(job_id=job.id, artifact_type="ERROR_REPORT_CSV", file_id=file_id))
    return file_id


def _save_export_csv(session: Session, job: CRMJob, rows: list[dict[str, Any]], fieldnames: list[str]) -> uuid.UUID:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    payload = output.getvalue().encode("utf-8")
    file_id = files_stub.store_bytes(payload, f"crm_job_{job.id}_export.csv", "text/csv")
    session.add(CRMJobArtifact(job_id=job.id, artifact_type="EXPORT_CSV", file_id=file_id))
    return file_id


def _import_accounts(
    session: Session,
    actor_user: Any,
    job: CRMJob,
    params: dict[str, Any],
    *,
    account_service: Any,
) -> dict[str, Any]:
    mapping = params.get("mapping") or {}
    source_file_id = uuid.UUID(params["source_file_id"])
    csv_bytes = files_stub.get_bytes(source_file_id)
    csv_text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(csv_text))

    name_column = mapping.get("name")
    if not name_column:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="mapping.name is required")

    fixed_legal_entity_ids = [uuid.UUID(value) for value in mapping.get("fixed_legal_entity_ids", [])]
    legal_entity_column = mapping.get("legal_entity_ids")

    created_count = 0
    updated_count = 0
    errors: list[dict[str, Any]] = []

    for index, raw_row in enumerate(reader, start=2):
        row = {key: (value.strip() if isinstance(value, str) else value) for key, value in raw_row.items()}
        row_name = row.get(name_column)
        if not row_name:
            errors.append(_row_error(index, "REQUIRED", "name is required", "name", row))
            continue

        try:
            legal_entity_ids = list(fixed_legal_entity_ids)
            if legal_entity_column:
                legal_entity_ids.extend(_parse_legal_entity_ids(row.get(legal_entity_column)))
            if not legal_entity_ids and actor_user.current_legal_entity_id is not None:
                legal_entity_ids = [actor_user.current_legal_entity_id]
            if not legal_entity_ids:
                raise ValueError("missing legal_entity_ids")

            dto = AccountCreate(
                name=row_name,
                owner_user_id=_parse_uuid(row.get(mapping.get("owner_user_id"))) if mapping.get("owner_user_id") else None,
                primary_region_code=row.get(mapping.get("primary_region_code")) if mapping.get("primary_region_code") else None,
                default_currency_code=row.get(mapping.get("default_currency_code")) if mapping.get("default_currency_code") else None,
                external_reference=row.get(mapping.get("external_reference")) if mapping.get("external_reference") else None,
                legal_entity_ids=legal_entity_ids,
            )
            created = account_service.create_account(
                session,
                actor_user_id=actor_user.user_id,
                dto=dto,
                legal_entity_ids=dto.legal_entity_ids,
                current_legal_entity_id=actor_user.current_legal_entity_id,
                correlation_id=actor_user.correlation_id,
            )
            created_count += 1

            if mapping.get("status") and row.get(mapping["status"]) and row.get(mapping["status"]) != created.status:
                account_service.update_account(
                    session,
                    actor_user,
                    created.id,
                    AccountUpdate(row_version=created.row_version, status=row.get(mapping["status"])),
                )
                updated_count += 1
        except ValidationError as exc:
            errors.append(_row_error(index, "VALIDATION", str(exc.errors()[0].get("msg", "invalid row")), "row", row))
        except HTTPException as exc:
            errors.append(_row_error(index, "HTTP_ERROR", str(exc.detail), "row", row))
        except Exception as exc:
            errors.append(_row_error(index, "ROW_ERROR", str(exc), "row", row))

    error_file_id = _save_error_report(session, job, errors)
    result: dict[str, Any] = {
        "created_count": created_count,
        "updated_count": updated_count,
        "error_count": len(errors),
    }
    if error_file_id:
        result["error_report_file_id"] = str(error_file_id)
    return result


def _import_contacts(
    session: Session,
    actor_user: Any,
    job: CRMJob,
    params: dict[str, Any],
    *,
    contact_service: Any,
) -> dict[str, Any]:
    mapping = params.get("mapping") or {}
    source_file_id = uuid.UUID(params["source_file_id"])
    csv_bytes = files_stub.get_bytes(source_file_id)
    csv_text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(csv_text))

    first_name_column = mapping.get("first_name")
    last_name_column = mapping.get("last_name")
    account_id_column = mapping.get("account_id")
    account_name_column = mapping.get("account_name")

    if not first_name_column or not last_name_column:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="mapping first_name and last_name are required")
    if not account_id_column and not account_name_column:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="mapping account_id or account_name is required")

    created_count = 0
    updated_count = 0
    errors: list[dict[str, Any]] = []

    for index, raw_row in enumerate(reader, start=2):
        row = {key: (value.strip() if isinstance(value, str) else value) for key, value in raw_row.items()}
        try:
            first_name = row.get(first_name_column)
            last_name = row.get(last_name_column)
            if not first_name:
                raise ValueError("first_name is required")
            if not last_name:
                raise ValueError("last_name is required")

            account_id: uuid.UUID | None = None
            if account_id_column:
                account_id = _parse_uuid(row.get(account_id_column))
            elif account_name_column:
                account_name = row.get(account_name_column)
                if not account_name:
                    raise ValueError("account_name is required")
                account = _visible_account_by_name(session, actor_user, account_name)
                if account is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
                account_id = account.id

            if account_id is None:
                raise ValueError("account_id is required")

            dto = ContactCreate(
                account_id=account_id,
                first_name=first_name,
                last_name=last_name,
                email=row.get(mapping.get("email")) if mapping.get("email") else None,
                phone=row.get(mapping.get("phone")) if mapping.get("phone") else None,
                title=row.get(mapping.get("title")) if mapping.get("title") else None,
                department=row.get(mapping.get("department")) if mapping.get("department") else None,
                owner_user_id=_parse_uuid(row.get(mapping.get("owner_user_id"))) if mapping.get("owner_user_id") else None,
                is_primary=_parse_bool(row.get(mapping.get("is_primary"))) if mapping.get("is_primary") else False,
            )
            contact_service.create_contact(session, actor_user, dto)
            created_count += 1
        except ValidationError as exc:
            errors.append(_row_error(index, "VALIDATION", str(exc.errors()[0].get("msg", "invalid row")), "row", row))
        except HTTPException as exc:
            errors.append(_row_error(index, "HTTP_ERROR", str(exc.detail), "row", row))
        except Exception as exc:
            errors.append(_row_error(index, "ROW_ERROR", str(exc), "row", row))

    error_file_id = _save_error_report(session, job, errors)
    result: dict[str, Any] = {
        "created_count": created_count,
        "updated_count": updated_count,
        "error_count": len(errors),
    }
    if error_file_id:
        result["error_report_file_id"] = str(error_file_id)
    return result


def _export_accounts(session: Session, actor_user: Any, job: CRMJob, params: dict[str, Any], *, account_service: Any) -> dict[str, Any]:
    filters = params.get("filters") or {}
    rows = account_service.list_accounts(session, actor_user, filters=filters, cursor=None, limit=1000)
    export_rows = [
        {
            "id": str(row.id),
            "name": row.name,
            "status": row.status,
            "owner_user_id": str(row.owner_user_id) if row.owner_user_id else "",
            "primary_region_code": row.primary_region_code or "",
            "default_currency_code": row.default_currency_code or "",
            "external_reference": row.external_reference or "",
            "legal_entity_ids": ";".join(str(item) for item in row.legal_entity_ids),
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
        for row in rows
    ]
    file_id = _save_export_csv(
        session,
        job,
        export_rows,
        [
            "id",
            "name",
            "status",
            "owner_user_id",
            "primary_region_code",
            "default_currency_code",
            "external_reference",
            "legal_entity_ids",
            "created_at",
            "updated_at",
        ],
    )
    return {"created_count": 0, "updated_count": 0, "error_count": 0, "export_file_id": str(file_id), "row_count": len(export_rows)}


def _export_contacts(session: Session, actor_user: Any, job: CRMJob, params: dict[str, Any]) -> dict[str, Any]:
    filters = params.get("filters") or {}

    stmt: Select[tuple[CRMContact, CRMAccount]] = (
        select(CRMContact, CRMAccount)
        .join(CRMAccount, CRMAccount.id == CRMContact.account_id)
        .join(CRMAccountLegalEntity, CRMAccountLegalEntity.account_id == CRMAccount.id)
        .where(and_(CRMContact.deleted_at.is_(None), CRMAccount.deleted_at.is_(None)))
        .distinct()
    )

    if "crm.contacts.read_all" not in actor_user.permissions:
        allowed = set(actor_user.allowed_legal_entity_ids)
        if not allowed:
            stmt = stmt.where(False)
        else:
            stmt = stmt.where(CRMAccountLegalEntity.legal_entity_id.in_(allowed))

    if filters.get("account_id"):
        stmt = stmt.where(CRMContact.account_id == uuid.UUID(str(filters["account_id"])))
    if filters.get("name"):
        q = f"%{str(filters['name'])}%"
        stmt = stmt.where(or_(CRMContact.first_name.ilike(q), CRMContact.last_name.ilike(q)))
    if filters.get("email"):
        stmt = stmt.where(CRMContact.email.ilike(f"%{str(filters['email'])}%"))
    if filters.get("owner_user_id"):
        stmt = stmt.where(CRMContact.owner_user_id == uuid.UUID(str(filters["owner_user_id"])))
    if filters.get("is_primary") is not None:
        stmt = stmt.where(CRMContact.is_primary.is_(bool(filters["is_primary"])))

    records = session.execute(stmt.order_by(CRMContact.updated_at.desc()).limit(1000)).all()
    export_rows: list[dict[str, Any]] = []
    for contact, account in records:
        export_rows.append(
            {
                "id": str(contact.id),
                "account_id": str(contact.account_id),
                "account_name": account.name,
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "email": contact.email or "",
                "phone": contact.phone or "",
                "title": contact.title or "",
                "department": contact.department or "",
                "owner_user_id": str(contact.owner_user_id) if contact.owner_user_id else "",
                "is_primary": str(contact.is_primary).lower(),
                "created_at": contact.created_at.isoformat(),
                "updated_at": contact.updated_at.isoformat(),
            }
        )

    file_id = _save_export_csv(
        session,
        job,
        export_rows,
        [
            "id",
            "account_id",
            "account_name",
            "first_name",
            "last_name",
            "email",
            "phone",
            "title",
            "department",
            "owner_user_id",
            "is_primary",
            "created_at",
            "updated_at",
        ],
    )
    return {"created_count": 0, "updated_count": 0, "error_count": 0, "export_file_id": str(file_id), "row_count": len(export_rows)}


def execute_job(session: Session, actor_user: Any, job: CRMJob, *, account_service: Any, contact_service: Any) -> dict[str, Any]:
    params = json.loads(job.params_json)

    if job.job_type == "CSV_IMPORT" and job.entity_type == "account":
        return _import_accounts(session, actor_user, job, params, account_service=account_service)
    if job.job_type == "CSV_IMPORT" and job.entity_type == "contact":
        return _import_contacts(session, actor_user, job, params, contact_service=contact_service)
    if job.job_type == "CSV_EXPORT" and job.entity_type == "account":
        return _export_accounts(session, actor_user, job, params, account_service=account_service)
    if job.job_type == "CSV_EXPORT" and job.entity_type == "contact":
        return _export_contacts(session, actor_user, job, params)

    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unsupported job type/entity")
