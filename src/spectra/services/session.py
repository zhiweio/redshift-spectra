"""Redshift Session management service for session reuse optimization.

This service manages Redshift Data API sessions, storing them in DynamoDB
and associating them with tenant users for connection reuse.
"""

from datetime import UTC, datetime
from typing import Any

import boto3
from aws_lambda_powertools import Logger, Tracer
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from spectra.utils.config import get_settings

logger = Logger()
tracer = Tracer()


class SessionError(Exception):
    """Base exception for session operations."""

    pass


class SessionNotFoundError(SessionError):
    """Raised when a session is not found."""

    pass


class SessionExpiredError(SessionError):
    """Raised when a session has expired."""

    pass


class RedshiftSession:
    """Represents a Redshift Data API session."""

    def __init__(
        self,
        session_id: str,
        tenant_id: str,
        db_user: str,
        created_at: datetime,
        expires_at: datetime,
        last_used_at: datetime,
        is_active: bool = True,
    ):
        self.session_id = session_id
        self.tenant_id = tenant_id
        self.db_user = db_user
        self.created_at = created_at
        self.expires_at = expires_at
        self.last_used_at = last_used_at
        self.is_active = is_active

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.now(UTC) >= self.expires_at

    @property
    def is_idle_expired(self) -> bool:
        """Check if session has exceeded idle timeout."""
        settings = get_settings()
        idle_seconds = (datetime.now(UTC) - self.last_used_at).total_seconds()
        return idle_seconds > settings.redshift_session_idle_timeout_seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DynamoDB storage."""
        return {
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "db_user": self.db_user,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat(),
            "is_active": self.is_active,
            "ttl": int(self.expires_at.timestamp()),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RedshiftSession":
        """Create from DynamoDB item."""
        return cls(
            session_id=data["session_id"],
            tenant_id=data["tenant_id"],
            db_user=data["db_user"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            last_used_at=datetime.fromisoformat(data["last_used_at"]),
            is_active=data.get("is_active", True),
        )


class SessionService:
    """Service for managing Redshift sessions in DynamoDB."""

    def __init__(self) -> None:
        """Initialize session service."""
        self.settings = get_settings()
        self.dynamodb = boto3.resource("dynamodb", region_name=self.settings.aws_region)
        self.table = self.dynamodb.Table(self.settings.dynamodb_sessions_table_name)

    @tracer.capture_method
    def get_active_session(self, tenant_id: str, db_user: str) -> RedshiftSession | None:
        """Get an active session for a tenant and db_user.

        Args:
            tenant_id: Tenant identifier
            db_user: Database user

        Returns:
            Active session if found, None otherwise
        """
        try:
            # Query sessions by tenant using GSI
            response = self.table.query(
                IndexName="gsi1-tenant",
                KeyConditionExpression=Key("tenant_id").eq(tenant_id),
                FilterExpression=Attr("db_user").eq(db_user) & Attr("is_active").eq(True),
            )

            for item in response.get("Items", []):
                session = RedshiftSession.from_dict(item)
                if not session.is_expired and not session.is_idle_expired:
                    logger.info(
                        "Found active session",
                        extra={
                            "session_id": session.session_id,
                            "tenant_id": tenant_id,
                            "db_user": db_user,
                        },
                    )
                    return session

            return None

        except ClientError as e:
            logger.error(
                "Failed to query sessions",
                extra={"error": str(e), "tenant_id": tenant_id},
            )
            return None

    @tracer.capture_method
    def create_session(
        self,
        session_id: str,
        tenant_id: str,
        db_user: str,
    ) -> RedshiftSession:
        """Create and store a new session.

        Args:
            session_id: Redshift session ID from Data API
            tenant_id: Tenant identifier
            db_user: Database user

        Returns:
            Created session
        """
        now = datetime.now(UTC)
        expires_at = datetime.fromtimestamp(
            now.timestamp() + self.settings.redshift_session_keep_alive_seconds,
            tz=UTC,
        )

        session = RedshiftSession(
            session_id=session_id,
            tenant_id=tenant_id,
            db_user=db_user,
            created_at=now,
            expires_at=expires_at,
            last_used_at=now,
            is_active=True,
        )

        try:
            self.table.put_item(Item=session.to_dict())
            logger.info(
                "Created new session",
                extra={
                    "session_id": session_id,
                    "tenant_id": tenant_id,
                    "db_user": db_user,
                    "expires_at": expires_at.isoformat(),
                },
            )
            return session

        except ClientError as e:
            logger.error("Failed to create session", extra={"error": str(e)})
            raise SessionError(f"Failed to create session: {e}")

    @tracer.capture_method
    def update_last_used(self, session_id: str) -> None:
        """Update the last_used_at timestamp for a session.

        Args:
            session_id: Session ID to update
        """
        now = datetime.now(UTC)
        try:
            self.table.update_item(
                Key={"session_id": session_id},
                UpdateExpression="SET last_used_at = :now",
                ExpressionAttributeValues={":now": now.isoformat()},
            )
        except ClientError as e:
            logger.warning(
                "Failed to update session last_used_at",
                extra={"session_id": session_id, "error": str(e)},
            )

    @tracer.capture_method
    def invalidate_session(self, session_id: str) -> None:
        """Mark a session as inactive.

        Args:
            session_id: Session ID to invalidate
        """
        try:
            self.table.update_item(
                Key={"session_id": session_id},
                UpdateExpression="SET is_active = :inactive",
                ExpressionAttributeValues={":inactive": False},
            )
            logger.info("Session invalidated", extra={"session_id": session_id})

        except ClientError as e:
            logger.warning(
                "Failed to invalidate session",
                extra={"session_id": session_id, "error": str(e)},
            )

    @tracer.capture_method
    def delete_session(self, session_id: str) -> None:
        """Delete a session from DynamoDB.

        Args:
            session_id: Session ID to delete
        """
        try:
            self.table.delete_item(Key={"session_id": session_id})
            logger.info("Session deleted", extra={"session_id": session_id})

        except ClientError as e:
            logger.warning(
                "Failed to delete session",
                extra={"session_id": session_id, "error": str(e)},
            )

    @tracer.capture_method
    def cleanup_expired_sessions(self, tenant_id: str) -> int:
        """Clean up expired sessions for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Number of sessions cleaned up
        """
        cleaned = 0
        try:
            response = self.table.query(
                IndexName="gsi1-tenant",
                KeyConditionExpression=Key("tenant_id").eq(tenant_id),
            )

            for item in response.get("Items", []):
                session = RedshiftSession.from_dict(item)
                if session.is_expired or session.is_idle_expired:
                    self.delete_session(session.session_id)
                    cleaned += 1

            if cleaned > 0:
                logger.info(
                    "Cleaned up expired sessions",
                    extra={"tenant_id": tenant_id, "count": cleaned},
                )

        except ClientError as e:
            logger.error(
                "Failed to cleanup sessions",
                extra={"tenant_id": tenant_id, "error": str(e)},
            )

        return cleaned

    @tracer.capture_method
    def get_or_create_session_id(
        self,
        tenant_id: str,
        db_user: str,
    ) -> tuple[str | None, bool]:
        """Get an existing session ID or indicate a new one is needed.

        Args:
            tenant_id: Tenant identifier
            db_user: Database user

        Returns:
            Tuple of (session_id or None, is_new_session)
            If session_id is None, caller should create a new session
        """
        existing = self.get_active_session(tenant_id, db_user)
        if existing:
            self.update_last_used(existing.session_id)
            return existing.session_id, False
        return None, True
