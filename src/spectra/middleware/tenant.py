"""Tenant context extraction middleware.

This module provides tenant context extraction from API Gateway events,
supporting multiple authentication modes (API Key, JWT, IAM).
"""

import json
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler.exceptions import UnauthorizedError
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

logger = Logger()


@dataclass
class TenantContext:
    """Tenant context extracted from authentication.

    This context is used throughout the request lifecycle to:
    - Set the database user for RLS/CLS enforcement
    - Track the tenant for audit logging
    - Apply tenant-specific rate limits and quotas
    """

    tenant_id: str
    db_user: str
    db_group: str | None = None
    permissions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    source_ip: str | None = None

    def __post_init__(self) -> None:
        """Validate tenant context."""
        if not self.tenant_id:
            raise ValueError("tenant_id is required")
        if not self.db_user:
            raise ValueError("db_user is required")

    def has_permission(self, permission: str) -> bool:
        """Check if tenant has a specific permission.

        Args:
            permission: Permission name to check

        Returns:
            True if tenant has the permission
        """
        return permission in self.permissions or "*" in self.permissions

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "tenant_id": self.tenant_id,
            "db_user": self.db_user,
            "db_group": self.db_group,
            "permissions": self.permissions,
            "request_id": self.request_id,
            "source_ip": self.source_ip,
        }


class TenantExtractionError(Exception):
    """Raised when tenant context cannot be extracted."""

    pass


def extract_tenant_context(event: APIGatewayProxyEvent | dict[str, Any]) -> TenantContext:
    """Extract tenant context from API Gateway event.

    Supports multiple authentication modes:
    - JWT token claims (from Lambda authorizer)
    - API Key metadata (from API Gateway usage plan)
    - IAM identity (from request context)
    - Custom headers (X-Tenant-ID, X-DB-User)

    Args:
        event: API Gateway event or dictionary

    Returns:
        TenantContext with extracted tenant information

    Raises:
        ValueError: If tenant context cannot be extracted
    """
    # Convert to dict if needed
    event_dict = event._data if isinstance(event, APIGatewayProxyEvent) else event

    # Get headers (case-insensitive)
    headers = _get_headers(event_dict)

    # Get request context
    request_context = event_dict.get("requestContext", {})
    request_id = request_context.get("requestId")
    source_ip = request_context.get("identity", {}).get("sourceIp")

    # Try extraction methods in order of preference
    tenant_ctx = None

    # 1. Try JWT claims from Lambda authorizer
    authorizer = request_context.get("authorizer", {})
    if authorizer:
        tenant_ctx = _extract_from_authorizer(authorizer, request_id, source_ip)

    # 2. Try API Key identity
    if not tenant_ctx:
        api_key_id = request_context.get("identity", {}).get("apiKeyId")
        if api_key_id:
            tenant_ctx = _extract_from_api_key(api_key_id, headers, request_id, source_ip)

    # 3. Try custom headers (development/testing)
    if not tenant_ctx:
        tenant_ctx = _extract_from_headers(headers, request_id, source_ip)

    if not tenant_ctx:
        raise ValueError("Unable to extract tenant context. Missing authentication.")

    logger.debug("Tenant context extracted", extra=tenant_ctx.to_dict())

    return tenant_ctx


def _get_headers(event: dict[str, Any]) -> dict[str, str]:
    """Get headers with case-insensitive keys.

    Args:
        event: API Gateway event

    Returns:
        Dictionary with lowercase header keys
    """
    raw_headers = event.get("headers") or {}
    return {k.lower(): v for k, v in raw_headers.items()}


def _extract_from_authorizer(
    authorizer: dict[str, Any],
    request_id: str | None,
    source_ip: str | None,
) -> TenantContext | None:
    """Extract tenant context from Lambda authorizer claims.

    Args:
        authorizer: Authorizer context from request
        request_id: Request ID for tracking
        source_ip: Source IP address

    Returns:
        TenantContext if extraction successful, None otherwise
    """
    # JWT claims might be in 'claims' or directly in authorizer context
    claims = authorizer.get("claims", {}) or authorizer

    tenant_id = claims.get("tenant_id") or claims.get("custom:tenant_id") or claims.get("sub")

    db_user = (
        claims.get("db_user") or claims.get("custom:db_user") or claims.get("cognito:username")
    )

    if not tenant_id or not db_user:
        return None

    db_group = claims.get("db_group") or claims.get("custom:db_group")

    # Parse permissions
    permissions_raw = claims.get("permissions", [])
    if isinstance(permissions_raw, str):
        try:
            permissions = json.loads(permissions_raw)
        except json.JSONDecodeError:
            permissions = permissions_raw.split(",")
    else:
        permissions = permissions_raw

    return TenantContext(
        tenant_id=tenant_id,
        db_user=db_user,
        db_group=db_group,
        permissions=permissions,
        metadata={"auth_type": "jwt"},
        request_id=request_id,
        source_ip=source_ip,
    )


def _extract_from_api_key(
    api_key_id: str,
    headers: dict[str, str],
    request_id: str | None,
    source_ip: str | None,
) -> TenantContext | None:
    """Extract tenant context from API Key.

    The API Key should be associated with a usage plan that has
    tenant metadata configured.

    Args:
        api_key_id: API Gateway API Key ID
        headers: Request headers
        request_id: Request ID for tracking
        source_ip: Source IP address

    Returns:
        TenantContext if extraction successful, None otherwise
    """
    # For API Key auth, tenant info comes from headers or API Key metadata
    tenant_id = headers.get("x-tenant-id")
    db_user = headers.get("x-db-user")

    # Derive tenant from API key ID pattern if not provided
    # Expected format: tenant-{tenant_id}
    if not tenant_id and api_key_id.startswith("tenant-"):
        tenant_id = api_key_id[7:]

    if not tenant_id or not db_user:
        return None

    return TenantContext(
        tenant_id=tenant_id,
        db_user=db_user,
        db_group=headers.get("x-db-group"),
        permissions=["query", "export"],  # Default permissions for API Key
        metadata={"auth_type": "api_key", "api_key_id": api_key_id},
        request_id=request_id,
        source_ip=source_ip,
    )


def _extract_from_headers(
    headers: dict[str, str],
    request_id: str | None,
    source_ip: str | None,
) -> TenantContext | None:
    """Extract tenant context from custom headers.

    This is primarily for development/testing purposes.
    In production, proper authentication should be used.

    Args:
        headers: Request headers
        request_id: Request ID for tracking
        source_ip: Source IP address

    Returns:
        TenantContext if extraction successful, None otherwise
    """
    tenant_id = headers.get("x-tenant-id")
    db_user = headers.get("x-db-user")

    if not tenant_id or not db_user:
        return None

    logger.warning(
        "Tenant context extracted from headers - should only be used in development",
        extra={"tenant_id": tenant_id, "db_user": db_user},
    )

    return TenantContext(
        tenant_id=tenant_id,
        db_user=db_user,
        db_group=headers.get("x-db-group"),
        permissions=headers.get("x-permissions", "query,export").split(","),
        metadata={"auth_type": "headers"},
        request_id=request_id,
        source_ip=source_ip,
    )


def require_permission(permission: str) -> Callable:
    """Decorator to require a specific permission.

    This decorator must be used with an APIResolver app that provides
    current_event access.

    Usage:
        @app.post("/admin")
        @require_permission("admin")
        def admin_only_endpoint():
            pass

    Args:
        permission: Required permission name

    Returns:
        Decorator function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # The event should be passed as the first argument or available via app
            # When used with APIResolver, the event is typically available via app.current_event
            # For direct Lambda handlers, the event is the first argument
            event = args[0] if args else kwargs.get("event")
            if event is None:
                raise ValueError("No event available for permission check")

            tenant_ctx = extract_tenant_context(event)

            if not tenant_ctx.has_permission(permission):
                raise UnauthorizedError(f"Missing required permission: {permission}")

            return func(*args, **kwargs)

        return wrapper

    return decorator
