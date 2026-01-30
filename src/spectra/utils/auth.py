"""Authentication utilities for Redshift Spectra."""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import boto3
from aws_lambda_powertools import Logger

from spectra.utils.config import get_settings

logger = Logger()


@dataclass
class TenantContext:
    """Tenant context extracted from authentication."""

    tenant_id: str
    db_user: str
    db_group: str | None = None
    permissions: list[str] | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Validate tenant context."""
        if not self.tenant_id:
            raise ValueError("tenant_id is required")
        if not self.db_user:
            raise ValueError("db_user is required")


class AuthenticationError(Exception):
    """Base exception for authentication errors."""

    pass


class InvalidTokenError(AuthenticationError):
    """Raised when token is invalid or malformed."""

    pass


class ExpiredTokenError(AuthenticationError):
    """Raised when token has expired."""

    pass


class MissingTenantError(AuthenticationError):
    """Raised when tenant ID is missing."""

    pass


def extract_tenant_from_event(event: dict[str, Any]) -> TenantContext:
    """Extract tenant context from API Gateway event.

    Args:
        event: API Gateway event

    Returns:
        TenantContext with tenant information

    Raises:
        MissingTenantError: If tenant ID cannot be determined
        AuthenticationError: If authentication fails
    """
    # Get headers (case-insensitive)
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    # Check for tenant ID in headers
    tenant_id = headers.get("x-tenant-id")

    # Also check path parameters for tenant-specific endpoints
    path_params = event.get("pathParameters") or {}
    if not tenant_id and "tenantId" in path_params:
        tenant_id = path_params["tenantId"]

    # Check request context for authorizer claims
    request_context = event.get("requestContext", {})
    authorizer = request_context.get("authorizer", {})

    if authorizer:
        # JWT claims from Lambda authorizer
        claims = authorizer.get("claims", {})
        if not tenant_id:
            tenant_id = claims.get("tenant_id") or claims.get("custom:tenant_id")

        # Get db_user from claims or derive from tenant
        db_user = claims.get("db_user") or claims.get("custom:db_user")
        db_group = claims.get("db_group") or claims.get("custom:db_group")
        permissions = claims.get("permissions", [])

        if isinstance(permissions, str):
            permissions = permissions.split(",")

        if tenant_id and db_user:
            return TenantContext(
                tenant_id=tenant_id,
                db_user=db_user,
                db_group=db_group,
                permissions=permissions,
                metadata={"source": "authorizer"},
            )

    if not tenant_id:
        raise MissingTenantError("Tenant ID not found in request headers or authorization token")

    # Derive db_user from tenant_id if not provided
    db_user = f"tenant_{tenant_id}"
    db_group = f"tenant_group_{tenant_id}"

    return TenantContext(
        tenant_id=tenant_id,
        db_user=db_user,
        db_group=db_group,
        metadata={"source": "header"},
    )


def validate_api_key(api_key: str) -> dict[str, Any]:
    """Validate an API key and return associated metadata.

    Args:
        api_key: The API key to validate

    Returns:
        Dictionary with tenant_id, db_user, and other metadata

    Raises:
        InvalidTokenError: If API key is invalid
    """
    # In production, this would validate against a database or cache
    # For now, we parse the key format: spectra_{tenant_id}_{hash}
    if not api_key.startswith("spectra_"):
        raise InvalidTokenError("Invalid API key format")

    parts = api_key.split("_", 2)
    if len(parts) != 3:
        raise InvalidTokenError("Invalid API key format")

    _, tenant_id, _key_hash = parts

    # TODO: Validate _key_hash against stored hash
    # For demo, we just return the parsed tenant

    return {
        "tenant_id": tenant_id,
        "db_user": f"tenant_{tenant_id}",
        "db_group": f"tenant_group_{tenant_id}",
    }


def get_secret(secret_arn: str) -> dict[str, Any]:
    """Retrieve secret from AWS Secrets Manager.

    Args:
        secret_arn: ARN of the secret

    Returns:
        Secret value as dictionary
    """
    settings = get_settings()
    client = boto3.client("secretsmanager", region_name=settings.aws_region)

    response = client.get_secret_value(SecretId=secret_arn)

    if "SecretString" in response:
        return json.loads(response["SecretString"])

    raise ValueError("Secret does not contain a string value")


def generate_api_key(tenant_id: str, secret: str) -> str:
    """Generate an API key for a tenant.

    Args:
        tenant_id: Tenant identifier
        secret: Secret key for HMAC

    Returns:
        Generated API key
    """
    timestamp = str(int(time.time()))
    message = f"{tenant_id}:{timestamp}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()[:32]

    return f"spectra_{tenant_id}_{signature}"


class LambdaAuthorizer:
    """Lambda authorizer for API Gateway."""

    def __init__(self) -> None:
        """Initialize authorizer."""
        self.settings = get_settings()

    def generate_policy(
        self,
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

    def authorize(self, event: dict[str, Any]) -> dict[str, Any]:
        """Authorize request based on token.

        Args:
            event: API Gateway authorizer event

        Returns:
            Authorization policy
        """
        # Get token from header
        token = event.get("authorizationToken", "")
        method_arn = event.get("methodArn", "*")

        if not token:
            logger.warning("No authorization token provided")
            return self.generate_policy("anonymous", "Deny", method_arn)

        # Remove Bearer prefix if present
        if token.startswith("Bearer "):
            token = token[7:]

        try:
            if self.settings.auth_mode == "api_key":
                metadata = validate_api_key(token)
            else:
                # JWT validation would go here
                raise NotImplementedError(f"Auth mode {self.settings.auth_mode} not implemented")

            logger.info("Authorization successful", extra={"tenant_id": metadata["tenant_id"]})

            return self.generate_policy(
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
            return self.generate_policy("anonymous", "Deny", method_arn)
