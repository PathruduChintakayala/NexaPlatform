from __future__ import annotations

from contextvars import ContextVar, Token

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
workflow_depth_var: ContextVar[int | None] = ContextVar("workflow_depth", default=None)


def set_correlation_id(value: str | None) -> Token[str | None]:
    return correlation_id_var.set(value)


def reset_correlation_id(token: Token[str | None]) -> None:
    correlation_id_var.reset(token)


def get_correlation_id() -> str | None:
    return correlation_id_var.get()


def set_workflow_depth(value: int | None) -> Token[int | None]:
    return workflow_depth_var.set(value)


def reset_workflow_depth(token: Token[int | None]) -> None:
    workflow_depth_var.reset(token)


def get_workflow_depth() -> int | None:
    return workflow_depth_var.get()


def get_log_context() -> dict[str, str | None]:
    return {"correlation_id": get_correlation_id()}
