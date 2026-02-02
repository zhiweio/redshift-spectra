"""Unit tests for session service.

Tests for the SessionService class that manages Redshift session reuse.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from spectra.services.session import (
    RedshiftSession,
    SessionError,
    SessionService,
)

# =============================================================================
# RedshiftSession Model Tests
# =============================================================================


class TestRedshiftSession:
    """Tests for RedshiftSession data class."""

    def test_create_session(self) -> None:
        """Test creating a session instance."""
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=1)

        session = RedshiftSession(
            session_id="session-123",
            tenant_id="tenant-456",
            db_user="user_tenant_456",
            created_at=now,
            expires_at=expires_at,
            last_used_at=now,
            is_active=True,
        )

        assert session.session_id == "session-123"
        assert session.tenant_id == "tenant-456"
        assert session.db_user == "user_tenant_456"
        assert session.is_active is True

    def test_session_not_expired(self) -> None:
        """Test session expiration check when not expired."""
        now = datetime.now(UTC)
        session = RedshiftSession(
            session_id="session-123",
            tenant_id="tenant-456",
            db_user="user_tenant_456",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            last_used_at=now,
        )

        assert session.is_expired is False

    def test_session_expired(self) -> None:
        """Test session expiration check when expired."""
        now = datetime.now(UTC)
        session = RedshiftSession(
            session_id="session-123",
            tenant_id="tenant-456",
            db_user="user_tenant_456",
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
            last_used_at=now - timedelta(hours=2),
        )

        assert session.is_expired is True

    def test_session_to_dict(self) -> None:
        """Test converting session to dictionary."""
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=1)

        session = RedshiftSession(
            session_id="session-123",
            tenant_id="tenant-456",
            db_user="user_tenant_456",
            created_at=now,
            expires_at=expires_at,
            last_used_at=now,
            is_active=True,
        )

        data = session.to_dict()

        assert data["session_id"] == "session-123"
        assert data["tenant_id"] == "tenant-456"
        assert data["db_user"] == "user_tenant_456"
        assert data["is_active"] is True
        assert "ttl" in data
        assert data["ttl"] == int(expires_at.timestamp())

    def test_session_from_dict(self) -> None:
        """Test creating session from dictionary."""
        now = datetime.now(UTC)
        data = {
            "session_id": "session-123",
            "tenant_id": "tenant-456",
            "db_user": "user_tenant_456",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            "last_used_at": now.isoformat(),
            "is_active": True,
        }

        session = RedshiftSession.from_dict(data)

        assert session.session_id == "session-123"
        assert session.tenant_id == "tenant-456"
        assert session.db_user == "user_tenant_456"
        assert session.is_active is True


# =============================================================================
# SessionService Tests
# =============================================================================


class TestSessionService:
    """Tests for SessionService class."""

    @pytest.fixture
    def mock_dynamodb_table(self) -> MagicMock:
        """Create a mock DynamoDB table."""
        return MagicMock()

    @pytest.fixture
    def session_service(self, mock_dynamodb_table: MagicMock) -> SessionService:
        """Create a SessionService with mocked dependencies."""
        with patch("boto3.resource") as mock_resource:
            mock_resource.return_value.Table.return_value = mock_dynamodb_table
            service = SessionService()
            service.table = mock_dynamodb_table
            return service

    def test_get_active_session_found(
        self, session_service: SessionService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test finding an active session."""
        now = datetime.now(UTC)
        mock_dynamodb_table.query.return_value = {
            "Items": [
                {
                    "session_id": "session-123",
                    "tenant_id": "tenant-456",
                    "db_user": "user_tenant_456",
                    "created_at": now.isoformat(),
                    "expires_at": (now + timedelta(hours=1)).isoformat(),
                    "last_used_at": now.isoformat(),
                    "is_active": True,
                }
            ]
        }

        session = session_service.get_active_session("tenant-456", "user_tenant_456")

        assert session is not None
        assert session.session_id == "session-123"
        mock_dynamodb_table.query.assert_called_once()

    def test_get_active_session_not_found(
        self, session_service: SessionService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test when no active session exists."""
        mock_dynamodb_table.query.return_value = {"Items": []}

        session = session_service.get_active_session("tenant-456", "user_tenant_456")

        assert session is None

    def test_get_active_session_expired(
        self, session_service: SessionService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test that expired sessions are not returned."""
        now = datetime.now(UTC)
        mock_dynamodb_table.query.return_value = {
            "Items": [
                {
                    "session_id": "session-123",
                    "tenant_id": "tenant-456",
                    "db_user": "user_tenant_456",
                    "created_at": (now - timedelta(hours=2)).isoformat(),
                    "expires_at": (now - timedelta(hours=1)).isoformat(),
                    "last_used_at": (now - timedelta(hours=2)).isoformat(),
                    "is_active": True,
                }
            ]
        }

        session = session_service.get_active_session("tenant-456", "user_tenant_456")

        assert session is None

    def test_get_active_session_client_error(
        self, session_service: SessionService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test handling of DynamoDB client error."""
        mock_dynamodb_table.query.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Error"}},
            "Query",
        )

        session = session_service.get_active_session("tenant-456", "user_tenant_456")

        assert session is None

    def test_create_session(
        self, session_service: SessionService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test creating a new session."""
        mock_dynamodb_table.put_item.return_value = {}

        session = session_service.create_session(
            session_id="session-123",
            tenant_id="tenant-456",
            db_user="user_tenant_456",
        )

        assert session.session_id == "session-123"
        assert session.tenant_id == "tenant-456"
        assert session.db_user == "user_tenant_456"
        assert session.is_active is True
        mock_dynamodb_table.put_item.assert_called_once()

    def test_create_session_error(
        self, session_service: SessionService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test handling of session creation error."""
        mock_dynamodb_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Error"}},
            "PutItem",
        )

        with pytest.raises(SessionError) as exc_info:
            session_service.create_session(
                session_id="session-123",
                tenant_id="tenant-456",
                db_user="user_tenant_456",
            )

        assert "Failed to create session" in str(exc_info.value)

    def test_update_last_used(
        self, session_service: SessionService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test updating session last_used_at."""
        mock_dynamodb_table.update_item.return_value = {}

        session_service.update_last_used("session-123")

        mock_dynamodb_table.update_item.assert_called_once()
        call_args = mock_dynamodb_table.update_item.call_args
        assert call_args.kwargs["Key"] == {"session_id": "session-123"}

    def test_invalidate_session(
        self, session_service: SessionService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test invalidating a session."""
        mock_dynamodb_table.update_item.return_value = {}

        session_service.invalidate_session("session-123")

        mock_dynamodb_table.update_item.assert_called_once()
        call_args = mock_dynamodb_table.update_item.call_args
        assert call_args.kwargs["ExpressionAttributeValues"][":inactive"] is False

    def test_delete_session(
        self, session_service: SessionService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test deleting a session."""
        mock_dynamodb_table.delete_item.return_value = {}

        session_service.delete_session("session-123")

        mock_dynamodb_table.delete_item.assert_called_once_with(Key={"session_id": "session-123"})

    def test_get_or_create_session_id_existing(
        self, session_service: SessionService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test get_or_create when session exists."""
        now = datetime.now(UTC)
        mock_dynamodb_table.query.return_value = {
            "Items": [
                {
                    "session_id": "session-123",
                    "tenant_id": "tenant-456",
                    "db_user": "user_tenant_456",
                    "created_at": now.isoformat(),
                    "expires_at": (now + timedelta(hours=1)).isoformat(),
                    "last_used_at": now.isoformat(),
                    "is_active": True,
                }
            ]
        }
        mock_dynamodb_table.update_item.return_value = {}

        session_id, is_new = session_service.get_or_create_session_id(
            "tenant-456", "user_tenant_456"
        )

        assert session_id == "session-123"
        assert is_new is False
        mock_dynamodb_table.update_item.assert_called_once()

    def test_get_or_create_session_id_new(
        self, session_service: SessionService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test get_or_create when no session exists."""
        mock_dynamodb_table.query.return_value = {"Items": []}

        session_id, is_new = session_service.get_or_create_session_id(
            "tenant-456", "user_tenant_456"
        )

        assert session_id is None
        assert is_new is True

    def test_cleanup_expired_sessions(
        self, session_service: SessionService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test cleaning up expired sessions."""
        now = datetime.now(UTC)
        mock_dynamodb_table.query.return_value = {
            "Items": [
                {
                    "session_id": "session-expired",
                    "tenant_id": "tenant-456",
                    "db_user": "user_tenant_456",
                    "created_at": (now - timedelta(hours=2)).isoformat(),
                    "expires_at": (now - timedelta(hours=1)).isoformat(),
                    "last_used_at": (now - timedelta(hours=2)).isoformat(),
                    "is_active": True,
                },
                {
                    "session_id": "session-active",
                    "tenant_id": "tenant-456",
                    "db_user": "user_tenant_456",
                    "created_at": now.isoformat(),
                    "expires_at": (now + timedelta(hours=1)).isoformat(),
                    "last_used_at": now.isoformat(),
                    "is_active": True,
                },
            ]
        }
        mock_dynamodb_table.delete_item.return_value = {}

        cleaned = session_service.cleanup_expired_sessions("tenant-456")

        assert cleaned == 1
        mock_dynamodb_table.delete_item.assert_called_once_with(
            Key={"session_id": "session-expired"}
        )
