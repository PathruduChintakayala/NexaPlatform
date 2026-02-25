from __future__ import annotations


class AuthorizationError(Exception):
    """Base authorization error for policy/FLS enforcement failures."""


class ForbiddenFieldError(AuthorizationError):
    """Raised when a payload contains fields that are not editable by policy."""

    def __init__(self, resource: str, fields: list[str]) -> None:
        self.resource = resource
        self.fields = sorted(set(fields))
        super().__init__(f"Forbidden fields for resource '{resource}': {', '.join(self.fields)}")
