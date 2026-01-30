"""Unit tests for tenant middleware.

Tests for the tenant context extraction middleware.
"""

from unittest.mock import patch

import pytest

from spectra.middleware.tenant import (
    TenantContext,
    _extract_from_api_key,
    _extract_from_authorizer,
    _extract_from_headers,
    _get_headers,
    extract_tenant_context,
    require_permission,
)

# =============================================================================
# TenantContext Tests
# =============================================================================


class TestTenantContext:
    """Tests for TenantContext dataclass."""

    def test_create_valid_context(self) -> None:
        """Test creating a valid tenant context."""
        ctx = TenantContext(
            tenant_id="tenant-123",
            db_user="user_tenant_123",
            db_group="analytics",
            permissions=["read", "query"],
            metadata={"plan": "enterprise"},
            request_id="req-abc",
            source_ip="192.168.1.1",
        )

        assert ctx.tenant_id == "tenant-123"
        assert ctx.db_user == "user_tenant_123"
        assert ctx.db_group == "analytics"
        assert ctx.permissions == ["read", "query"]

    def test_create_minimal_context(self) -> None:
        """Test creating a context with minimal required fields."""
        ctx = TenantContext(
            tenant_id="tenant-123",
            db_user="user_tenant_123",
        )

        assert ctx.tenant_id == "tenant-123"
        assert ctx.db_user == "user_tenant_123"
        assert ctx.db_group is None
        assert ctx.permissions == []

    def test_missing_tenant_id_raises(self) -> None:
        """Test that missing tenant_id raises ValueError."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            TenantContext(
                tenant_id="",
                db_user="user_tenant_123",
            )

    def test_missing_db_user_raises(self) -> None:
        """Test that missing db_user raises ValueError."""
        with pytest.raises(ValueError, match="db_user is required"):
            TenantContext(
                tenant_id="tenant-123",
                db_user="",
            )

    def test_has_permission_true(self) -> None:
        """Test has_permission returns True for existing permission."""
        ctx = TenantContext(
            tenant_id="tenant-123",
            db_user="user_tenant_123",
            permissions=["read", "query", "export"],
        )

        assert ctx.has_permission("read") is True
        assert ctx.has_permission("query") is True

    def test_has_permission_false(self) -> None:
        """Test has_permission returns False for missing permission."""
        ctx = TenantContext(
            tenant_id="tenant-123",
            db_user="user_tenant_123",
            permissions=["read"],
        )

        assert ctx.has_permission("admin") is False
        assert ctx.has_permission("delete") is False

    def test_has_permission_wildcard(self) -> None:
        """Test has_permission with wildcard permission."""
        ctx = TenantContext(
            tenant_id="tenant-123",
            db_user="user_tenant_123",
            permissions=["*"],
        )

        assert ctx.has_permission("anything") is True
        assert ctx.has_permission("admin") is True

    def test_to_dict(self) -> None:
        """Test converting context to dictionary."""
        ctx = TenantContext(
            tenant_id="tenant-123",
            db_user="user_tenant_123",
            db_group="analytics",
            permissions=["read"],
            request_id="req-abc",
            source_ip="192.168.1.1",
        )

        data = ctx.to_dict()

        assert data["tenant_id"] == "tenant-123"
        assert data["db_user"] == "user_tenant_123"
        assert data["db_group"] == "analytics"
        assert data["permissions"] == ["read"]
        assert data["request_id"] == "req-abc"
        assert data["source_ip"] == "192.168.1.1"


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestGetHeaders:
    """Tests for _get_headers helper function."""

    def test_normalizes_header_keys(self) -> None:
        """Test that header keys are normalized to lowercase."""
        event = {
            "headers": {
                "Content-Type": "application/json",
                "X-Tenant-ID": "tenant-123",
                "AUTHORIZATION": "Bearer token",
            }
        }

        headers = _get_headers(event)

        assert headers["content-type"] == "application/json"
        assert headers["x-tenant-id"] == "tenant-123"
        assert headers["authorization"] == "Bearer token"

    def test_handles_none_headers(self) -> None:
        """Test handling of None headers."""
        event = {"headers": None}

        headers = _get_headers(event)

        assert headers == {}

    def test_handles_missing_headers(self) -> None:
        """Test handling of missing headers key."""
        event = {}

        headers = _get_headers(event)

        assert headers == {}


class TestExtractFromAuthorizer:
    """Tests for _extract_from_authorizer helper function."""

    def test_extract_from_jwt_claims(self) -> None:
        """Test extracting context from JWT claims."""
        authorizer = {
            "claims": {
                "tenant_id": "tenant-123",
                "db_user": "user_tenant_123",
                "db_group": "analytics",
                "permissions": ["read", "query"],
            }
        }

        ctx = _extract_from_authorizer(authorizer, "req-123", "192.168.1.1")

        assert ctx is not None
        assert ctx.tenant_id == "tenant-123"
        assert ctx.db_user == "user_tenant_123"
        assert ctx.db_group == "analytics"

    def test_extract_with_custom_claims(self) -> None:
        """Test extracting context with custom: prefix claims."""
        authorizer = {
            "claims": {
                "custom:tenant_id": "tenant-123",
                "custom:db_user": "user_tenant_123",
                "custom:db_group": "analytics",
            }
        }

        ctx = _extract_from_authorizer(authorizer, None, None)

        assert ctx is not None
        assert ctx.tenant_id == "tenant-123"
        assert ctx.db_user == "user_tenant_123"

    def test_extract_with_sub_fallback(self) -> None:
        """Test using 'sub' as fallback for tenant_id."""
        authorizer = {
            "claims": {
                "sub": "user-123",
                "cognito:username": "user_tenant_123",
            }
        }

        ctx = _extract_from_authorizer(authorizer, None, None)

        assert ctx is not None
        assert ctx.tenant_id == "user-123"
        assert ctx.db_user == "user_tenant_123"

    def test_extract_permissions_as_string(self) -> None:
        """Test parsing permissions from comma-separated string."""
        authorizer = {
            "claims": {
                "tenant_id": "tenant-123",
                "db_user": "user_tenant_123",
                "permissions": "read,query,export",
            }
        }

        ctx = _extract_from_authorizer(authorizer, None, None)

        assert ctx is not None
        assert ctx.permissions == ["read", "query", "export"]

    def test_extract_permissions_as_json_string(self) -> None:
        """Test parsing permissions from JSON string."""
        authorizer = {
            "claims": {
                "tenant_id": "tenant-123",
                "db_user": "user_tenant_123",
                "permissions": '["read", "query"]',
            }
        }

        ctx = _extract_from_authorizer(authorizer, None, None)

        assert ctx is not None
        assert ctx.permissions == ["read", "query"]

    def test_returns_none_without_tenant_id(self) -> None:
        """Test returns None when tenant_id is missing."""
        authorizer = {
            "claims": {
                "db_user": "user_tenant_123",
            }
        }

        ctx = _extract_from_authorizer(authorizer, None, None)

        assert ctx is None

    def test_returns_none_without_db_user(self) -> None:
        """Test returns None when db_user is missing."""
        authorizer = {
            "claims": {
                "tenant_id": "tenant-123",
            }
        }

        ctx = _extract_from_authorizer(authorizer, None, None)

        assert ctx is None


class TestExtractFromApiKey:
    """Tests for _extract_from_api_key helper function."""

    def test_extract_with_headers(self) -> None:
        """Test extracting context from headers with API key."""
        headers = {
            "x-tenant-id": "tenant-123",
            "x-db-user": "user_tenant_123",
            "x-db-group": "analytics",
        }

        ctx = _extract_from_api_key("api-key-id", headers, "req-123", "192.168.1.1")

        assert ctx is not None
        assert ctx.tenant_id == "tenant-123"
        assert ctx.db_user == "user_tenant_123"
        assert ctx.metadata["auth_type"] == "api_key"

    def test_extract_tenant_from_key_pattern(self) -> None:
        """Test extracting tenant ID from API key pattern."""
        headers = {
            "x-db-user": "user_tenant_123",
        }

        ctx = _extract_from_api_key("tenant-123", headers, None, None)

        assert ctx is not None
        assert ctx.tenant_id == "123"

    def test_returns_none_without_required_fields(self) -> None:
        """Test returns None when required fields are missing."""
        headers = {}

        ctx = _extract_from_api_key("api-key-id", headers, None, None)

        assert ctx is None

    def test_default_permissions(self) -> None:
        """Test that default permissions are set for API key auth."""
        headers = {
            "x-tenant-id": "tenant-123",
            "x-db-user": "user_tenant_123",
        }

        ctx = _extract_from_api_key("api-key-id", headers, None, None)

        assert ctx is not None
        assert "query" in ctx.permissions
        assert "export" in ctx.permissions


class TestExtractFromHeaders:
    """Tests for _extract_from_headers helper function."""

    def test_extract_basic_headers(self) -> None:
        """Test extracting context from basic headers."""
        headers = {
            "x-tenant-id": "tenant-123",
            "x-db-user": "user_tenant_123",
        }

        ctx = _extract_from_headers(headers, "req-123", "192.168.1.1")

        assert ctx is not None
        assert ctx.tenant_id == "tenant-123"
        assert ctx.db_user == "user_tenant_123"
        assert ctx.metadata["auth_type"] == "headers"

    def test_extract_with_optional_headers(self) -> None:
        """Test extracting context with all optional headers."""
        headers = {
            "x-tenant-id": "tenant-123",
            "x-db-user": "user_tenant_123",
            "x-db-group": "analytics",
            "x-permissions": "read,query,admin",
        }

        ctx = _extract_from_headers(headers, None, None)

        assert ctx is not None
        assert ctx.db_group == "analytics"
        assert ctx.permissions == ["read", "query", "admin"]

    def test_default_permissions(self) -> None:
        """Test default permissions when not specified."""
        headers = {
            "x-tenant-id": "tenant-123",
            "x-db-user": "user_tenant_123",
        }

        ctx = _extract_from_headers(headers, None, None)

        assert ctx is not None
        assert "query" in ctx.permissions
        assert "export" in ctx.permissions

    def test_returns_none_without_tenant_id(self) -> None:
        """Test returns None when tenant_id is missing."""
        headers = {
            "x-db-user": "user_tenant_123",
        }

        ctx = _extract_from_headers(headers, None, None)

        assert ctx is None


# =============================================================================
# Main Extraction Function Tests
# =============================================================================


class TestExtractTenantContext:
    """Tests for extract_tenant_context function."""

    def test_extract_from_authorizer_priority(self) -> None:
        """Test that authorizer takes priority over headers."""
        event = {
            "headers": {
                "x-tenant-id": "header-tenant",
                "x-db-user": "header-user",
            },
            "requestContext": {
                "requestId": "req-123",
                "identity": {"sourceIp": "192.168.1.1"},
                "authorizer": {
                    "claims": {
                        "tenant_id": "auth-tenant",
                        "db_user": "auth-user",
                    }
                },
            },
        }

        ctx = extract_tenant_context(event)

        assert ctx.tenant_id == "auth-tenant"
        assert ctx.db_user == "auth-user"

    def test_extract_from_api_key(self) -> None:
        """Test extraction from API key."""
        event = {
            "headers": {
                "x-tenant-id": "tenant-123",
                "x-db-user": "user_tenant_123",
            },
            "requestContext": {
                "requestId": "req-123",
                "identity": {
                    "sourceIp": "192.168.1.1",
                    "apiKeyId": "api-key-123",
                },
            },
        }

        ctx = extract_tenant_context(event)

        assert ctx.tenant_id == "tenant-123"
        assert ctx.metadata["auth_type"] == "api_key"

    def test_extract_from_headers_fallback(self) -> None:
        """Test extraction falls back to headers."""
        event = {
            "headers": {
                "x-tenant-id": "tenant-123",
                "x-db-user": "user_tenant_123",
            },
            "requestContext": {
                "requestId": "req-123",
                "identity": {"sourceIp": "192.168.1.1"},
            },
        }

        ctx = extract_tenant_context(event)

        assert ctx.tenant_id == "tenant-123"
        assert ctx.metadata["auth_type"] == "headers"

    def test_raises_when_no_auth(self) -> None:
        """Test raises ValueError when no authentication found."""
        event = {
            "headers": {},
            "requestContext": {
                "requestId": "req-123",
                "identity": {"sourceIp": "192.168.1.1"},
            },
        }

        with pytest.raises(ValueError, match="Unable to extract tenant context"):
            extract_tenant_context(event)

    def test_sets_request_context_fields(self) -> None:
        """Test that request ID and source IP are set."""
        event = {
            "headers": {
                "x-tenant-id": "tenant-123",
                "x-db-user": "user_tenant_123",
            },
            "requestContext": {
                "requestId": "req-abc-123",
                "identity": {"sourceIp": "10.0.0.1"},
            },
        }

        ctx = extract_tenant_context(event)

        assert ctx.request_id == "req-abc-123"
        assert ctx.source_ip == "10.0.0.1"


# =============================================================================
# Decorator Tests
# =============================================================================


class TestRequirePermission:
    """Tests for require_permission decorator."""

    def test_allows_with_permission(self) -> None:
        """Test that function is called when permission exists."""
        with patch("spectra.middleware.tenant.extract_tenant_context") as mock_extract:
            mock_extract.return_value = TenantContext(
                tenant_id="tenant-123",
                db_user="user_tenant_123",
                permissions=["admin", "read"],
            )

            @require_permission("admin")
            def admin_function(event):
                return "success"

            # Pass a mock event as argument
            result = admin_function({"test": "event"})

            assert result == "success"

    def test_denies_without_permission(self) -> None:
        """Test that UnauthorizedError is raised without permission."""
        from aws_lambda_powertools.event_handler.exceptions import UnauthorizedError

        with patch("spectra.middleware.tenant.extract_tenant_context") as mock_extract:
            mock_extract.return_value = TenantContext(
                tenant_id="tenant-123",
                db_user="user_tenant_123",
                permissions=["read"],
            )

            @require_permission("admin")
            def admin_function(event):
                return "success"

            with pytest.raises(UnauthorizedError, match="Missing required permission"):
                admin_function({"test": "event"})
