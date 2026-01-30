"""Unit tests for auth utilities.

Tests for authentication and authorization utilities.
"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spectra.utils.auth import (
    AuthenticationError,
    ExpiredTokenError,
    InvalidTokenError,
    LambdaAuthorizer,
    MissingTenantError,
    TenantContext,
    extract_tenant_from_event,
    generate_api_key,
    get_secret,
    validate_api_key,
)


# =============================================================================
# TenantContext Tests
# =============================================================================


class TestTenantContext:
    """Tests for TenantContext dataclass."""

    def test_create_full_context(self) -> None:
        """Test creating a context with all fields."""
        ctx = TenantContext(
            tenant_id="tenant-123",
            db_user="user_tenant_123",
            db_group="analytics",
            permissions=["read", "query"],
            metadata={"plan": "enterprise"},
        )

        assert ctx.tenant_id == "tenant-123"
        assert ctx.db_user == "user_tenant_123"
        assert ctx.db_group == "analytics"
        assert ctx.permissions == ["read", "query"]
        assert ctx.metadata == {"plan": "enterprise"}

    def test_create_minimal_context(self) -> None:
        """Test creating a context with minimal fields."""
        ctx = TenantContext(
            tenant_id="tenant-123",
            db_user="user_tenant_123",
        )

        assert ctx.tenant_id == "tenant-123"
        assert ctx.db_user == "user_tenant_123"
        assert ctx.db_group is None
        assert ctx.permissions is None
        assert ctx.metadata is None

    def test_missing_tenant_id_raises(self) -> None:
        """Test that missing tenant_id raises ValueError."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            TenantContext(tenant_id="", db_user="user")

    def test_missing_db_user_raises(self) -> None:
        """Test that missing db_user raises ValueError."""
        with pytest.raises(ValueError, match="db_user is required"):
            TenantContext(tenant_id="tenant", db_user="")


# =============================================================================
# Extract Tenant Tests
# =============================================================================


class TestExtractTenantFromEvent:
    """Tests for extract_tenant_from_event function."""

    def test_extract_from_headers(self) -> None:
        """Test extracting tenant from headers."""
        event = {
            "headers": {
                "x-tenant-id": "tenant-123",
            },
            "requestContext": {},
        }

        ctx = extract_tenant_from_event(event)

        assert ctx.tenant_id == "tenant-123"
        assert ctx.db_user == "tenant_tenant-123"
        assert ctx.metadata == {"source": "header"}

    def test_extract_from_path_parameters(self) -> None:
        """Test extracting tenant from path parameters."""
        event = {
            "headers": {},
            "pathParameters": {"tenantId": "tenant-456"},
            "requestContext": {},
        }

        ctx = extract_tenant_from_event(event)

        assert ctx.tenant_id == "tenant-456"

    def test_extract_from_authorizer_claims(self) -> None:
        """Test extracting tenant from authorizer claims."""
        event = {
            "headers": {},
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "tenant_id": "tenant-789",
                        "db_user": "user_789",
                        "db_group": "analytics",
                        "permissions": ["read", "query"],
                    }
                }
            },
        }

        ctx = extract_tenant_from_event(event)

        assert ctx.tenant_id == "tenant-789"
        assert ctx.db_user == "user_789"
        assert ctx.db_group == "analytics"
        assert ctx.permissions == ["read", "query"]

    def test_extract_from_custom_claims(self) -> None:
        """Test extracting tenant from custom: prefixed claims."""
        event = {
            "headers": {},
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "custom:tenant_id": "tenant-custom",
                        "custom:db_user": "custom_user",
                    }
                }
            },
        }

        ctx = extract_tenant_from_event(event)

        assert ctx.tenant_id == "tenant-custom"
        assert ctx.db_user == "custom_user"

    def test_permissions_as_comma_string(self) -> None:
        """Test parsing permissions from comma-separated string."""
        event = {
            "headers": {},
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "tenant_id": "tenant-123",
                        "db_user": "user_123",
                        "permissions": "read,write,delete",
                    }
                }
            },
        }

        ctx = extract_tenant_from_event(event)

        assert ctx.permissions == ["read", "write", "delete"]

    def test_missing_tenant_raises(self) -> None:
        """Test that missing tenant raises MissingTenantError."""
        event = {
            "headers": {},
            "requestContext": {},
        }

        with pytest.raises(MissingTenantError):
            extract_tenant_from_event(event)


# =============================================================================
# API Key Validation Tests
# =============================================================================


class TestValidateApiKey:
    """Tests for validate_api_key function."""

    def test_valid_api_key(self) -> None:
        """Test validating a correctly formatted API key."""
        api_key = "spectra_tenant123_abcdef1234567890"

        result = validate_api_key(api_key)

        assert result["tenant_id"] == "tenant123"
        assert result["db_user"] == "tenant_tenant123"
        assert result["db_group"] == "tenant_group_tenant123"

    def test_invalid_prefix_raises(self) -> None:
        """Test that invalid prefix raises InvalidTokenError."""
        with pytest.raises(InvalidTokenError, match="Invalid API key format"):
            validate_api_key("invalid_tenant123_hash")

    def test_invalid_format_raises(self) -> None:
        """Test that invalid format raises InvalidTokenError."""
        # This key has an invalid middle part (less than 3 parts)
        with pytest.raises(InvalidTokenError):
            validate_api_key("spectra_tenantonly")

    def test_missing_parts_raises(self) -> None:
        """Test that missing parts raises InvalidTokenError."""
        with pytest.raises(InvalidTokenError, match="Invalid API key format"):
            validate_api_key("spectra_tenantonly")


# =============================================================================
# API Key Generation Tests
# =============================================================================


class TestGenerateApiKey:
    """Tests for generate_api_key function."""

    def test_generates_valid_format(self) -> None:
        """Test that generated key has valid format."""
        api_key = generate_api_key("tenant123", "secret-key")

        assert api_key.startswith("spectra_tenant123_")
        parts = api_key.split("_")
        assert len(parts) == 3
        assert len(parts[2]) == 32  # HMAC signature length

    def test_deterministic_for_same_time(self) -> None:
        """Test that keys are deterministic for same timestamp."""
        with patch("time.time", return_value=1234567890):
            key1 = generate_api_key("tenant123", "secret")
            key2 = generate_api_key("tenant123", "secret")

        assert key1 == key2

    def test_different_for_different_tenants(self) -> None:
        """Test that different tenants get different keys."""
        with patch("time.time", return_value=1234567890):
            key1 = generate_api_key("tenant1", "secret")
            key2 = generate_api_key("tenant2", "secret")

        assert key1 != key2


# =============================================================================
# Get Secret Tests
# =============================================================================


class TestGetSecret:
    """Tests for get_secret function."""

    def test_get_secret_success(self) -> None:
        """Test successfully retrieving a secret."""
        with patch("boto3.client") as mock_client:
            mock_sm = MagicMock()
            mock_client.return_value = mock_sm
            mock_sm.get_secret_value.return_value = {
                "SecretString": json.dumps({"username": "admin", "password": "secret"})
            }

            result = get_secret("arn:aws:secretsmanager:us-east-1:123:secret:test")

            assert result["username"] == "admin"
            assert result["password"] == "secret"

    def test_get_secret_no_string_raises(self) -> None:
        """Test that missing SecretString raises ValueError."""
        with patch("boto3.client") as mock_client:
            mock_sm = MagicMock()
            mock_client.return_value = mock_sm
            mock_sm.get_secret_value.return_value = {"SecretBinary": b"binary"}

            with pytest.raises(ValueError, match="Secret does not contain a string"):
                get_secret("arn:aws:secretsmanager:us-east-1:123:secret:test")


# =============================================================================
# Lambda Authorizer Tests
# =============================================================================


class TestLambdaAuthorizer:
    """Tests for LambdaAuthorizer class."""

    @pytest.fixture
    def authorizer(self) -> LambdaAuthorizer:
        """Create a LambdaAuthorizer instance."""
        with patch("spectra.utils.auth.get_settings") as mock_settings:
            mock_settings.return_value.auth_mode = "api_key"
            mock_settings.return_value.aws_region = "us-east-1"
            return LambdaAuthorizer()

    def test_generate_policy_allow(self, authorizer: LambdaAuthorizer) -> None:
        """Test generating an Allow policy."""
        policy = authorizer.generate_policy(
            principal_id="tenant-123",
            effect="Allow",
            resource="arn:aws:execute-api:*:*:*/*/GET/*",
        )

        assert policy["principalId"] == "tenant-123"
        statement = policy["policyDocument"]["Statement"][0]
        assert statement["Effect"] == "Allow"
        assert statement["Action"] == "execute-api:Invoke"

    def test_generate_policy_deny(self, authorizer: LambdaAuthorizer) -> None:
        """Test generating a Deny policy."""
        policy = authorizer.generate_policy(
            principal_id="anonymous",
            effect="Deny",
            resource="*",
        )

        assert policy["principalId"] == "anonymous"
        statement = policy["policyDocument"]["Statement"][0]
        assert statement["Effect"] == "Deny"

    def test_generate_policy_with_context(self, authorizer: LambdaAuthorizer) -> None:
        """Test generating policy with context."""
        policy = authorizer.generate_policy(
            principal_id="tenant-123",
            effect="Allow",
            resource="*",
            context={
                "tenant_id": "tenant-123",
                "db_user": "user_tenant_123",
                "permissions": ["read", "query"],
            },
        )

        assert "context" in policy
        assert policy["context"]["tenant_id"] == "tenant-123"
        # Non-string values should be stringified
        assert policy["context"]["permissions"] == "['read', 'query']"

    def test_authorize_with_valid_api_key(self, authorizer: LambdaAuthorizer) -> None:
        """Test authorization with valid API key."""
        event = {
            "authorizationToken": "spectra_tenant123_abcdef1234567890abcdef12",
            "methodArn": "arn:aws:execute-api:us-east-1:123:api/stage/GET/resource",
        }

        policy = authorizer.authorize(event)

        assert policy["principalId"] == "tenant123"
        statement = policy["policyDocument"]["Statement"][0]
        assert statement["Effect"] == "Allow"

    def test_authorize_with_bearer_prefix(self, authorizer: LambdaAuthorizer) -> None:
        """Test authorization with Bearer prefix."""
        event = {
            "authorizationToken": "Bearer spectra_tenant123_abcdef1234567890abcdef12",
            "methodArn": "*",
        }

        policy = authorizer.authorize(event)

        assert policy["principalId"] == "tenant123"
        statement = policy["policyDocument"]["Statement"][0]
        assert statement["Effect"] == "Allow"

    def test_authorize_without_token(self, authorizer: LambdaAuthorizer) -> None:
        """Test authorization without token."""
        event = {
            "authorizationToken": "",
            "methodArn": "*",
        }

        policy = authorizer.authorize(event)

        assert policy["principalId"] == "anonymous"
        statement = policy["policyDocument"]["Statement"][0]
        assert statement["Effect"] == "Deny"

    def test_authorize_with_invalid_token(self, authorizer: LambdaAuthorizer) -> None:
        """Test authorization with invalid token."""
        event = {
            "authorizationToken": "invalid_token_format",
            "methodArn": "*",
        }

        policy = authorizer.authorize(event)

        assert policy["principalId"] == "anonymous"
        statement = policy["policyDocument"]["Statement"][0]
        assert statement["Effect"] == "Deny"


# =============================================================================
# Exception Tests
# =============================================================================


class TestAuthExceptions:
    """Tests for authentication exceptions."""

    def test_authentication_error(self) -> None:
        """Test base AuthenticationError."""
        error = AuthenticationError("Auth failed")
        assert str(error) == "Auth failed"
        assert isinstance(error, Exception)

    def test_invalid_token_error(self) -> None:
        """Test InvalidTokenError."""
        error = InvalidTokenError("Token malformed")
        assert str(error) == "Token malformed"
        assert isinstance(error, AuthenticationError)

    def test_expired_token_error(self) -> None:
        """Test ExpiredTokenError."""
        error = ExpiredTokenError("Token expired")
        assert str(error) == "Token expired"
        assert isinstance(error, AuthenticationError)

    def test_missing_tenant_error(self) -> None:
        """Test MissingTenantError."""
        error = MissingTenantError("Tenant not found")
        assert str(error) == "Tenant not found"
        assert isinstance(error, AuthenticationError)
