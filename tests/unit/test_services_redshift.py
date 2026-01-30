"""Unit tests for Redshift service.

Tests for the RedshiftService class that handles query execution via Data API.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from spectra.services.redshift import (
    QueryExecutionError,
    RedshiftError,
    RedshiftService,
    SessionCreationError,
    StatementNotFoundError,
)


# =============================================================================
# RedshiftService Tests
# =============================================================================


class TestRedshiftService:
    """Tests for RedshiftService class."""

    @pytest.fixture
    def mock_redshift_client(self) -> MagicMock:
        """Create a mock Redshift Data API client."""
        return MagicMock()

    @pytest.fixture
    def mock_session_service(self) -> MagicMock:
        """Create a mock SessionService."""
        return MagicMock()

    @pytest.fixture
    def redshift_service(
        self, mock_redshift_client: MagicMock, mock_session_service: MagicMock
    ) -> RedshiftService:
        """Create a RedshiftService with mocked dependencies."""
        with patch("boto3.client") as mock_client:
            mock_client.return_value = mock_redshift_client
            with patch("spectra.services.redshift.SessionService") as mock_ss:
                mock_ss.return_value = mock_session_service
                service = RedshiftService()
                service.client = mock_redshift_client
                service.session_service = mock_session_service
                return service

    def test_execute_statement_basic(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
        mock_session_service: MagicMock,
    ) -> None:
        """Test basic statement execution."""
        mock_session_service.get_or_create_session_id.return_value = (None, True)
        mock_redshift_client.execute_statement.return_value = {
            "Id": "stmt-123",
            "SessionId": "session-456",
        }

        statement_id = redshift_service.execute_statement(
            sql="SELECT * FROM sales",
            db_user="user_tenant_123",
            tenant_id="tenant-123",
        )

        assert statement_id == "stmt-123"
        mock_redshift_client.execute_statement.assert_called_once()

    def test_execute_statement_with_session_reuse(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
        mock_session_service: MagicMock,
    ) -> None:
        """Test statement execution with session reuse."""
        mock_session_service.get_or_create_session_id.return_value = (
            "existing-session-123",
            False,
        )
        mock_redshift_client.execute_statement.return_value = {
            "Id": "stmt-123",
            "SessionId": "existing-session-123",
        }

        redshift_service.execute_statement(
            sql="SELECT * FROM sales",
            db_user="user_tenant_123",
            tenant_id="tenant-123",
            use_session=True,
        )

        call_args = mock_redshift_client.execute_statement.call_args
        assert call_args.kwargs["SessionId"] == "existing-session-123"

    def test_execute_statement_creates_new_session(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
        mock_session_service: MagicMock,
    ) -> None:
        """Test that a new session is created when needed."""
        mock_session_service.get_or_create_session_id.return_value = (None, True)
        mock_redshift_client.execute_statement.return_value = {
            "Id": "stmt-123",
            "SessionId": "new-session-456",
        }

        redshift_service.execute_statement(
            sql="SELECT * FROM sales",
            db_user="user_tenant_123",
            tenant_id="tenant-123",
        )

        # Should store the new session
        mock_session_service.create_session.assert_called_once_with(
            session_id="new-session-456",
            tenant_id="tenant-123",
            db_user="user_tenant_123",
        )

    def test_execute_statement_without_session(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
        mock_session_service: MagicMock,
    ) -> None:
        """Test statement execution without session reuse."""
        mock_redshift_client.execute_statement.return_value = {"Id": "stmt-123"}

        redshift_service.execute_statement(
            sql="SELECT * FROM sales",
            db_user="user_tenant_123",
            tenant_id="tenant-123",
            use_session=False,
        )

        call_args = mock_redshift_client.execute_statement.call_args
        assert "SessionId" not in call_args.kwargs
        assert "SessionKeepAliveSeconds" not in call_args.kwargs

    def test_execute_statement_with_parameters(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
        mock_session_service: MagicMock,
    ) -> None:
        """Test statement execution with parameters."""
        mock_session_service.get_or_create_session_id.return_value = (None, True)
        mock_redshift_client.execute_statement.return_value = {"Id": "stmt-123"}

        params = [
            {"name": "status", "value": "active"},
            {"name": "limit", "value": "100"},
        ]

        redshift_service.execute_statement(
            sql="SELECT * FROM sales WHERE status = :status LIMIT :limit",
            db_user="user_tenant_123",
            tenant_id="tenant-123",
            parameters=params,
        )

        call_args = mock_redshift_client.execute_statement.call_args
        assert call_args.kwargs["Parameters"] == params

    def test_execute_statement_with_statement_name(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
        mock_session_service: MagicMock,
    ) -> None:
        """Test statement execution with statement name."""
        mock_session_service.get_or_create_session_id.return_value = (None, True)
        mock_redshift_client.execute_statement.return_value = {"Id": "stmt-123"}

        redshift_service.execute_statement(
            sql="SELECT * FROM sales",
            db_user="user_tenant_123",
            tenant_id="tenant-123",
            statement_name="daily_sales_report",
        )

        call_args = mock_redshift_client.execute_statement.call_args
        assert call_args.kwargs["StatementName"] == "daily_sales_report"

    def test_execute_statement_with_event(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
        mock_session_service: MagicMock,
    ) -> None:
        """Test statement execution with CloudWatch event enabled."""
        mock_session_service.get_or_create_session_id.return_value = (None, True)
        mock_redshift_client.execute_statement.return_value = {"Id": "stmt-123"}

        redshift_service.execute_statement(
            sql="SELECT * FROM sales",
            db_user="user_tenant_123",
            tenant_id="tenant-123",
            with_event=True,
        )

        call_args = mock_redshift_client.execute_statement.call_args
        assert call_args.kwargs["WithEvent"] is True


class TestRedshiftServiceErrors:
    """Tests for RedshiftService error handling."""

    @pytest.fixture
    def mock_redshift_client(self) -> MagicMock:
        """Create a mock Redshift Data API client."""
        return MagicMock()

    @pytest.fixture
    def mock_session_service(self) -> MagicMock:
        """Create a mock SessionService."""
        return MagicMock()

    @pytest.fixture
    def redshift_service(
        self, mock_redshift_client: MagicMock, mock_session_service: MagicMock
    ) -> RedshiftService:
        """Create a RedshiftService with mocked dependencies."""
        with patch("boto3.client") as mock_client:
            mock_client.return_value = mock_redshift_client
            with patch("spectra.services.redshift.SessionService") as mock_ss:
                mock_ss.return_value = mock_session_service
                service = RedshiftService()
                service.client = mock_redshift_client
                service.session_service = mock_session_service
                return service

    def test_execute_statement_client_error(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
        mock_session_service: MagicMock,
    ) -> None:
        """Test handling of client error on execute."""
        from spectra.services.redshift import QueryExecutionError

        mock_session_service.get_or_create_session_id.return_value = (None, True)
        mock_redshift_client.execute_statement.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ValidationException",
                    "Message": "Invalid SQL syntax",
                }
            },
            "ExecuteStatement",
        )

        with pytest.raises(QueryExecutionError):
            redshift_service.execute_statement(
                sql="INVALID SQL",
                db_user="user_tenant_123",
                tenant_id="tenant-123",
            )

    def test_execute_statement_session_error_retry(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
        mock_session_service: MagicMock,
    ) -> None:
        """Test that session errors trigger retry without session."""
        mock_session_service.get_or_create_session_id.return_value = (
            "bad-session",
            False,
        )

        # First call fails with session error
        session_error = ClientError(
            {
                "Error": {
                    "Code": "ValidationException",
                    "Message": "Session bad-session is not valid",
                }
            },
            "ExecuteStatement",
        )

        # Second call succeeds without session
        mock_redshift_client.execute_statement.side_effect = [
            session_error,
            {"Id": "stmt-123"},
        ]

        statement_id = redshift_service.execute_statement(
            sql="SELECT * FROM sales",
            db_user="user_tenant_123",
            tenant_id="tenant-123",
        )

        assert statement_id == "stmt-123"
        mock_session_service.invalidate_session.assert_called_once_with("bad-session")


class TestRedshiftExceptions:
    """Tests for Redshift exception classes."""

    def test_redshift_error(self) -> None:
        """Test base RedshiftError."""
        error = RedshiftError(
            message="Test error",
            code="TEST_ERROR",
            details={"key": "value"},
        )

        assert str(error) == "Test error"
        assert error.code == "TEST_ERROR"
        assert error.details == {"key": "value"}

    def test_query_execution_error(self) -> None:
        """Test QueryExecutionError."""
        error = QueryExecutionError("Query failed", code="QUERY_FAILED")

        assert isinstance(error, RedshiftError)
        assert str(error) == "Query failed"
        assert error.code == "QUERY_FAILED"

    def test_statement_not_found_error(self) -> None:
        """Test StatementNotFoundError."""
        error = StatementNotFoundError("Statement not found")

        assert isinstance(error, RedshiftError)
        assert str(error) == "Statement not found"

    def test_session_creation_error(self) -> None:
        """Test SessionCreationError."""
        error = SessionCreationError("Failed to create session")

        assert isinstance(error, RedshiftError)
        assert str(error) == "Failed to create session"
