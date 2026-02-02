"""Lambda Authorizer handler.

This handler validates API tokens and returns IAM policies for API Gateway.
Supports multiple authentication modes: JWT, API Key, and IAM.
"""

from typing import Any

import jwt
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from spectra.utils.auth import (
    AuthenticationError,
    InvalidTokenError,
    get_secret,
    validate_api_key,
)
from spectra.utils.config import get_settings

logger = Logger()
tracer = Tracer()


class JWTValidator:
    """JWT token validator."""

    def __init__(self) -> None:
        """Initialize JWT validator with settings."""
        self.settings = get_settings()
        self._secret: str | None = None

    @property
    def secret(self) -> str:
        """Get JWT secret from Secrets Manager (cached)."""
        if self._secret is None:
            if self.settings.jwt_secret_arn:
                secret_data = get_secret(self.settings.jwt_secret_arn)
                # Support both 'secret' and 'jwt_secret' keys
                self._secret = secret_data.get("secret") or secret_data.get("jwt_secret", "")
            else:
                self._secret = self.settings.jwt_secret or ""
        return self._secret

    def validate(self, token: str) -> dict[str, Any]:
        """Validate JWT token and return claims.

        Args:
            token: JWT token string

        Returns:
            Decoded JWT claims

        Raises:
            InvalidTokenError: If token is invalid or expired
        """
        try:
            # Decode and validate JWT
            claims = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                audience=self.settings.jwt_audience,
                issuer=self.settings.jwt_issuer,
            )

            return {
                "tenant_id": claims.get("tenant_id") or claims.get("sub"),
                "db_user": claims.get(
                    "db_user", f"tenant_{claims.get('tenant_id', claims.get('sub'))}"
                ),
                "db_group": claims.get("db_group"),
                "permissions": claims.get("permissions", []),
            }

        except jwt.ExpiredSignatureError:
            raise InvalidTokenError("Token has expired")
        except jwt.InvalidAudienceError:
            raise InvalidTokenError("Invalid token audience")
        except jwt.InvalidIssuerError:
            raise InvalidTokenError("Invalid token issuer")
        except jwt.DecodeError as e:
            raise InvalidTokenError(f"Failed to decode token: {e}")
        except Exception as e:
            raise InvalidTokenError(f"Token validation failed: {e}")


def generate_policy(
    principal_id: str,
    effect: str,
    resource: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate IAM policy document.

    Args:
        principal_id: The principal user/tenant ID
        effect: Allow or Deny
        resource: The resource ARN
        context: Additional context to pass to downstream Lambda

    Returns:
        IAM policy document
    """
    policy: dict[str, Any] = {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": resource,
                }
            ],
        },
    }

    if context:
        # Flatten context for API Gateway
        policy["context"] = {
            k: str(v) if not isinstance(v, str | int | bool) else v for k, v in context.items()
        }

    return policy


@tracer.capture_lambda_handler
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:  # noqa: ARG001
    """Lambda Authorizer handler.

    Args:
        event: API Gateway authorizer event
        context: Lambda context

    Returns:
        IAM policy document
    """
    settings = get_settings()

    # Get token from header
    token = event.get("authorizationToken", "")
    method_arn = event.get("methodArn", "*")

    logger.info(
        "Processing authorization request",
        extra={
            "method_arn": method_arn,
            "auth_mode": settings.auth_mode,
            "has_token": bool(token),
        },
    )

    if not token:
        logger.warning("No authorization token provided")
        return generate_policy("anonymous", "Deny", method_arn)

    # Remove Bearer prefix if present
    if token.startswith("Bearer "):
        token = token[7:]

    try:
        if settings.auth_mode == "api_key":
            metadata = validate_api_key(token)
        elif settings.auth_mode == "jwt":
            validator = JWTValidator()
            metadata = validator.validate(token)
        elif settings.auth_mode == "none":
            # No authentication - allow all with default tenant
            metadata = {
                "tenant_id": "default",
                "db_user": "default_user",
                "db_group": "default_group",
            }
        else:
            raise InvalidTokenError(f"Unsupported auth mode: {settings.auth_mode}")

        logger.info(
            "Authorization successful",
            extra={
                "tenant_id": metadata["tenant_id"],
            },
        )

        return generate_policy(
            principal_id=metadata["tenant_id"],
            effect="Allow",
            resource=method_arn,
            context={
                "tenant_id": metadata["tenant_id"],
                "db_user": metadata["db_user"],
                "db_group": metadata.get("db_group", ""),
            },
        )

    except AuthenticationError as e:
        logger.warning("Authorization failed", extra={"error": str(e)})
        return generate_policy("anonymous", "Deny", method_arn)
    except Exception as e:
        logger.error("Unexpected authorization error", extra={"error": str(e)})
        return generate_policy("anonymous", "Deny", method_arn)
