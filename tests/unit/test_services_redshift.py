"""Unit tests for Redshift service.

Tests for the RedshiftService class that handles query execution via Data API.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from spectra.services.redshift import (
    QueryExecutionError,
    QueryTimeoutError,
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

    def test_query_timeout_error(self) -> None:
        """Test QueryTimeoutError."""
        error = QueryTimeoutError("Query timed out", code="QUERY_TIMEOUT")

        assert isinstance(error, RedshiftError)
        assert str(error) == "Query timed out"
        assert error.code == "QUERY_TIMEOUT"

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


class TestGetAllStatementResults:
    """Tests for get_all_statement_results with pagination."""

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

    def test_get_all_results_single_page(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
    ) -> None:
        """Test fetching results when data fits in single page."""
        mock_redshift_client.get_statement_result_v2.return_value = {
            "ColumnMetadata": [
                {"name": "id", "typeName": "int4"},
                {"name": "name", "typeName": "varchar"},
            ],
            "FormattedRecords": "1,Alice\n2,Bob\n3,Charlie\n",
            "TotalNumRows": 3,
            # No NextToken - single page
        }

        result = redshift_service.get_all_statement_results("stmt-123")

        assert len(result["records"]) == 3
        assert result["total_rows"] == 3
        assert result["pages_fetched"] == 1
        assert len(result["columns"]) == 2
        assert result["records"][0] == {"id": "1", "name": "Alice"}

    def test_get_all_results_multiple_pages(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
    ) -> None:
        """Test fetching results with pagination across multiple pages."""
        # Simulate 3 pages of results
        mock_redshift_client.get_statement_result_v2.side_effect = [
            {
                "ColumnMetadata": [{"name": "id", "typeName": "int4"}],
                "FormattedRecords": "1\n2\n3\n",
                "TotalNumRows": 9,
                "NextToken": "token-page-2",
            },
            {
                "ColumnMetadata": [{"name": "id", "typeName": "int4"}],
                "FormattedRecords": "4\n5\n6\n",
                "TotalNumRows": 9,
                "NextToken": "token-page-3",
            },
            {
                "ColumnMetadata": [{"name": "id", "typeName": "int4"}],
                "FormattedRecords": "7\n8\n9\n",
                "TotalNumRows": 9,
                # No NextToken - last page
            },
        ]

        result = redshift_service.get_all_statement_results("stmt-123")

        assert len(result["records"]) == 9
        assert result["total_rows"] == 9
        assert result["pages_fetched"] == 3
        # Verify all records are present
        ids = [r["id"] for r in result["records"]]
        assert ids == ["1", "2", "3", "4", "5", "6", "7", "8", "9"]

    def test_get_all_results_with_max_rows(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
    ) -> None:
        """Test fetching results stops at max_rows limit."""
        # First page has 5 records, we set max_rows to 3
        mock_redshift_client.get_statement_result_v2.return_value = {
            "ColumnMetadata": [{"name": "id", "typeName": "int4"}],
            "FormattedRecords": "1\n2\n3\n4\n5\n",
            "TotalNumRows": 100,
            "NextToken": "token-page-2",
        }

        result = redshift_service.get_all_statement_results("stmt-123", max_rows=3)

        assert len(result["records"]) == 3
        # Should stop after first page since we have enough
        assert result["pages_fetched"] == 1
        assert result["records"] == [{"id": "1"}, {"id": "2"}, {"id": "3"}]

    def test_get_all_results_max_rows_spans_pages(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
    ) -> None:
        """Test max_rows limit that requires fetching multiple pages."""
        mock_redshift_client.get_statement_result_v2.side_effect = [
            {
                "ColumnMetadata": [{"name": "id", "typeName": "int4"}],
                "FormattedRecords": "1\n2\n",
                "TotalNumRows": 10,
                "NextToken": "token-page-2",
            },
            {
                "ColumnMetadata": [{"name": "id", "typeName": "int4"}],
                "FormattedRecords": "3\n4\n",
                "TotalNumRows": 10,
                "NextToken": "token-page-3",
            },
            {
                "ColumnMetadata": [{"name": "id", "typeName": "int4"}],
                "FormattedRecords": "5\n6\n",
                "TotalNumRows": 10,
                "NextToken": "token-page-4",
            },
        ]

        # max_rows=5 should fetch 3 pages (2+2+2 records, truncate to 5)
        result = redshift_service.get_all_statement_results("stmt-123", max_rows=5)

        assert len(result["records"]) == 5
        assert result["pages_fetched"] == 3

    def test_get_all_results_empty_result(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
    ) -> None:
        """Test fetching empty result set."""
        mock_redshift_client.get_statement_result_v2.return_value = {
            "ColumnMetadata": [{"name": "id", "typeName": "int4"}],
            "FormattedRecords": "",
            "TotalNumRows": 0,
        }

        result = redshift_service.get_all_statement_results("stmt-123")

        assert len(result["records"]) == 0
        assert result["total_rows"] == 0
        assert result["pages_fetched"] == 1

    def test_get_all_results_typed_format_fallback(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
    ) -> None:
        """Test fallback to typed format when CSV not supported."""
        # CSV format fails
        mock_redshift_client.get_statement_result_v2.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ValidationException",
                    "Message": "CSV format not supported",
                }
            },
            "GetStatementResultV2",
        )
        # Typed format succeeds
        mock_redshift_client.get_statement_result.return_value = {
            "ColumnMetadata": [{"name": "id", "typeName": "int4"}],
            "Records": [
                [{"longValue": 1}],
                [{"longValue": 2}],
            ],
            "TotalNumRows": 2,
        }

        result = redshift_service.get_all_statement_results("stmt-123")

        assert len(result["records"]) == 2
        assert result["format"] == "TYPED"


class TestWaitForStatement:
    """Tests for wait_for_statement method."""

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

    def test_wait_for_statement_success(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
    ) -> None:
        """Test waiting for a statement that completes successfully."""
        mock_redshift_client.describe_statement.side_effect = [
            {"Id": "stmt-123", "Status": "STARTED"},
            {"Id": "stmt-123", "Status": "STARTED"},
            {"Id": "stmt-123", "Status": "FINISHED", "ResultRows": 100, "Duration": 5000},
        ]

        result = redshift_service.wait_for_statement(
            "stmt-123", timeout_seconds=10, poll_interval_seconds=0.01
        )

        assert result["status"] == "FINISHED"
        assert result["result_rows"] == 100

    def test_wait_for_statement_timeout(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
    ) -> None:
        """Test waiting for a statement that times out."""
        # Always return STARTED status
        mock_redshift_client.describe_statement.return_value = {
            "Id": "stmt-123",
            "Status": "STARTED",
        }

        with pytest.raises(QueryTimeoutError) as exc_info:
            redshift_service.wait_for_statement(
                "stmt-123", timeout_seconds=0.1, poll_interval_seconds=0.01
            )

        assert "timeout" in str(exc_info.value).lower()

    def test_wait_for_statement_failed(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
    ) -> None:
        """Test waiting for a statement that fails."""
        mock_redshift_client.describe_statement.return_value = {
            "Id": "stmt-123",
            "Status": "FAILED",
            "Error": "Syntax error at line 1",
        }

        with pytest.raises(QueryExecutionError) as exc_info:
            redshift_service.wait_for_statement("stmt-123", timeout_seconds=10)

        assert "failed" in str(exc_info.value).lower()

    def test_wait_for_statement_aborted(
        self,
        redshift_service: RedshiftService,
        mock_redshift_client: MagicMock,
    ) -> None:
        """Test waiting for a statement that was aborted."""
        mock_redshift_client.describe_statement.return_value = {
            "Id": "stmt-123",
            "Status": "ABORTED",
        }

        with pytest.raises(QueryExecutionError) as exc_info:
            redshift_service.wait_for_statement("stmt-123", timeout_seconds=10)

        assert "cancelled" in str(exc_info.value).lower()
