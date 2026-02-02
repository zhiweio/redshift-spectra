"""Unit tests for Lambda Authorizer handler.

Tests cover:
- JWT validation
- API key validation
- Policy generation
- Error handling
"""

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest


def create_authorizer_event(
    token: str | None = None,
    method_arn: str = "arn:aws:execute-api:us-east-1:123456789012:api-id/stage/GET/resource",
) -> dict:
    """Create a mock API Gateway authorizer event."""
    event = {
        "type": "TOKEN",
        "methodArn": method_arn,
        "authorizationToken": token or "",
    }
    return event


@pytest.fixture
def mock_context():
    """Create a mock Lambda context."""
    context = MagicMock()
    context.function_name = "spectra-authorizer"
    context.aws_request_id = "req-123"
    return context


class TestGeneratePolicy:
    """Tests for policy generation function."""

    def test_generate_allow_policy(self):
        """Test generating an Allow policy."""
        from spectra.handlers.authorizer import generate_policy

        policy = generate_policy(
            principal_id="tenant-123",
            effect="Allow",
            resource="arn:aws:execute-api:us-east-1:123456789012:api/*/GET/*",
        )

        assert policy["principalId"] == "tenant-123"
        assert policy["policyDocument"]["Version"] == "2012-10-17"
        statement = policy["policyDocument"]["Statement"][0]
        assert statement["Effect"] == "Allow"
        assert statement["Action"] == "execute-api:Invoke"

    def test_generate_deny_policy(self):
        """Test generating a Deny policy."""
        from spectra.handlers.authorizer import generate_policy

        policy = generate_policy(
            principal_id="anonymous",
            effect="Deny",
            resource="*",
        )

        statement = policy["policyDocument"]["Statement"][0]
        assert statement["Effect"] == "Deny"

    def test_generate_policy_with_context(self):
        """Test generating policy with context."""
        from spectra.handlers.authorizer import generate_policy

        policy = generate_policy(
            principal_id="tenant-123",
            effect="Allow",
            resource="*",
            context={
                "tenant_id": "tenant-123",
                "db_user": "user_tenant_123",
                "db_group": "analytics",
            },
        )

        assert "context" in policy
        assert policy["context"]["tenant_id"] == "tenant-123"
        assert policy["context"]["db_user"] == "user_tenant_123"

    def test_generate_policy_flattens_non_primitives(self):
        """Test that non-primitive context values are converted to strings."""
        from spectra.handlers.authorizer import generate_policy

        policy = generate_policy(
            principal_id="tenant-123",
            effect="Allow",
            resource="*",
            context={
                "permissions": ["read", "write"],  # List should be stringified
                "count": 42,  # Int should stay as int
                "active": True,  # Bool should stay as bool
            },
        )

        assert policy["context"]["permissions"] == "['read', 'write']"
        assert policy["context"]["count"] == 42
        assert policy["context"]["active"] is True


class TestJWTValidator:
    """Tests for JWT validation."""

    @pytest.fixture
    def jwt_secret(self) -> str:
        """JWT secret for testing."""
        return "test-secret-key-12345"

    def test_validate_valid_token(self, jwt_secret):
        """Test validating a valid JWT token."""
        from spectra.handlers.authorizer import JWTValidator

        # Create a valid token
        payload = {
            "tenant_id": "tenant-123",
            "db_user": "user_tenant_123",
            "db_group": "analytics",
            "permissions": ["query:read", "query:write"],
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        with patch("spectra.handlers.authorizer.get_settings") as mock_settings:
            settings = MagicMock()
            settings.jwt_secret_arn = None
            settings.jwt_secret = jwt_secret
            settings.jwt_audience = None
            settings.jwt_issuer = None
            mock_settings.return_value = settings

            validator = JWTValidator()
            result = validator.validate(token)

            assert result["tenant_id"] == "tenant-123"
            assert result["db_user"] == "user_tenant_123"
            assert result["db_group"] == "analytics"

    def test_validate_expired_token(self, jwt_secret):
        """Test that expired token raises error."""
        from spectra.handlers.authorizer import JWTValidator
        from spectra.utils.auth import InvalidTokenError

        # Create an expired token
        payload = {
            "tenant_id": "tenant-123",
            "exp": int(time.time()) - 3600,  # Expired 1 hour ago
        }
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        with patch("spectra.handlers.authorizer.get_settings") as mock_settings:
            settings = MagicMock()
            settings.jwt_secret_arn = None
            settings.jwt_secret = jwt_secret
            settings.jwt_audience = None
            settings.jwt_issuer = None
            mock_settings.return_value = settings

            validator = JWTValidator()
            with pytest.raises(InvalidTokenError, match="expired"):
                validator.validate(token)

    def test_validate_invalid_signature(self, jwt_secret):
        """Test that token with invalid signature raises error."""
        from spectra.handlers.authorizer import JWTValidator
        from spectra.utils.auth import InvalidTokenError

        # Create a token signed with wrong key
        payload = {"tenant_id": "tenant-123", "exp": int(time.time()) + 3600}
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")

        with patch("spectra.handlers.authorizer.get_settings") as mock_settings:
            settings = MagicMock()
            settings.jwt_secret_arn = None
            settings.jwt_secret = jwt_secret
            settings.jwt_audience = None
            settings.jwt_issuer = None
            mock_settings.return_value = settings

            validator = JWTValidator()
            with pytest.raises(InvalidTokenError):
                validator.validate(token)

    def test_validate_uses_sub_fallback(self, jwt_secret):
        """Test that 'sub' claim is used as fallback for tenant_id."""
        from spectra.handlers.authorizer import JWTValidator

        payload = {
            "sub": "user-456",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        with patch("spectra.handlers.authorizer.get_settings") as mock_settings:
            settings = MagicMock()
            settings.jwt_secret_arn = None
            settings.jwt_secret = jwt_secret
            settings.jwt_audience = None
            settings.jwt_issuer = None
            mock_settings.return_value = settings

            validator = JWTValidator()
            result = validator.validate(token)

            assert result["tenant_id"] == "user-456"
            assert result["db_user"] == "tenant_user-456"


class TestAuthorizerHandler:
    """Tests for authorizer Lambda handler."""

    def test_handler_no_token_returns_deny(self, mock_context):
        """Test handler returns Deny when no token is provided."""
        from spectra.handlers.authorizer import handler

        event = create_authorizer_event(token=None)

        with patch("spectra.handlers.authorizer.get_settings") as mock_settings:
            settings = MagicMock()
            settings.auth_mode = "jwt"
            mock_settings.return_value = settings

            result = handler(event, mock_context)

            assert result["principalId"] == "anonymous"
            statement = result["policyDocument"]["Statement"][0]
            assert statement["Effect"] == "Deny"

    def test_handler_api_key_mode(self, mock_context):
        """Test handler with API key authentication mode."""
        from spectra.handlers.authorizer import handler

        event = create_authorizer_event(token="sk_test_tenant123_abc123")

        with patch("spectra.handlers.authorizer.get_settings") as mock_settings:
            settings = MagicMock()
            settings.auth_mode = "api_key"
            mock_settings.return_value = settings

            with patch("spectra.handlers.authorizer.validate_api_key") as mock_validate:
                mock_validate.return_value = {
                    "tenant_id": "tenant-123",
                    "db_user": "user_tenant_123",
                    "db_group": "analytics",
                }

                result = handler(event, mock_context)

                assert result["principalId"] == "tenant-123"
                statement = result["policyDocument"]["Statement"][0]
                assert statement["Effect"] == "Allow"
                assert result["context"]["tenant_id"] == "tenant-123"

    def test_handler_removes_bearer_prefix(self, mock_context):
        """Test handler removes 'Bearer ' prefix from token."""
        from spectra.handlers.authorizer import handler

        event = create_authorizer_event(token="Bearer actual-token")

        with patch("spectra.handlers.authorizer.get_settings") as mock_settings:
            settings = MagicMock()
            settings.auth_mode = "api_key"
            mock_settings.return_value = settings

            with patch("spectra.handlers.authorizer.validate_api_key") as mock_validate:
                mock_validate.return_value = {
                    "tenant_id": "tenant-123",
                    "db_user": "user_tenant_123",
                }

                handler(event, mock_context)

                # Verify Bearer prefix was stripped
                mock_validate.assert_called_once_with("actual-token")

    def test_handler_auth_error_returns_deny(self, mock_context):
        """Test handler returns Deny on authentication error."""
        from spectra.handlers.authorizer import handler
        from spectra.utils.auth import AuthenticationError

        event = create_authorizer_event(token="invalid-token")

        with patch("spectra.handlers.authorizer.get_settings") as mock_settings:
            settings = MagicMock()
            settings.auth_mode = "api_key"
            mock_settings.return_value = settings

            with patch("spectra.handlers.authorizer.validate_api_key") as mock_validate:
                mock_validate.side_effect = AuthenticationError("Invalid API key")

                result = handler(event, mock_context)

                assert result["principalId"] == "anonymous"
                statement = result["policyDocument"]["Statement"][0]
                assert statement["Effect"] == "Deny"

    def test_handler_none_auth_mode(self, mock_context):
        """Test handler with 'none' authentication mode allows all."""
        from spectra.handlers.authorizer import handler

        event = create_authorizer_event(token="any-token")

        with patch("spectra.handlers.authorizer.get_settings") as mock_settings:
            settings = MagicMock()
            settings.auth_mode = "none"
            mock_settings.return_value = settings

            result = handler(event, mock_context)

            assert result["principalId"] == "default"
            statement = result["policyDocument"]["Statement"][0]
            assert statement["Effect"] == "Allow"
            assert result["context"]["tenant_id"] == "default"
