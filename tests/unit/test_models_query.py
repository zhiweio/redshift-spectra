"""Unit tests for query models.

Tests cover:
- QueryParameter validation
- QueryRequest validation (sync-only API)
- QueryResponse serialization
- ResultMetadata for truncation handling
- BulkQueryItem validation
- Edge cases and error handling
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from spectra.models.query import (
    BulkQueryItem,
    OutputFormat,
    QueryParameter,
    QueryRequest,
    QueryResponse,
    ResultMetadata,
)


class TestQueryParameter:
    """Tests for QueryParameter model."""

    def test_valid_parameter(self) -> None:
        """Test creating valid parameter."""
        param = QueryParameter(name="user_id", value=123)
        assert param.name == "user_id"
        assert param.value == 123

    def test_string_value(self) -> None:
        """Test parameter with string value."""
        param = QueryParameter(name="status", value="active")
        assert param.value == "active"

    def test_boolean_value(self) -> None:
        """Test parameter with boolean value."""
        param = QueryParameter(name="active", value=True)
        assert param.value is True

    def test_null_value(self) -> None:
        """Test parameter with null value."""
        param = QueryParameter(name="optional", value=None)
        assert param.value is None

    def test_invalid_name_with_spaces(self) -> None:
        """Test that parameter name with spaces is rejected."""
        with pytest.raises(ValidationError):
            QueryParameter(name="invalid name", value=1)

    def test_invalid_name_starting_with_number(self) -> None:
        """Test that parameter name starting with number is rejected."""
        with pytest.raises(ValidationError):
            QueryParameter(name="123param", value=1)

    def test_empty_name_rejected(self) -> None:
        """Test that empty parameter name is rejected."""
        with pytest.raises(ValidationError):
            QueryParameter(name="", value=1)

    def test_name_max_length(self) -> None:
        """Test parameter name max length validation."""
        # Should work with 128 chars
        param = QueryParameter(name="a" * 128, value=1)
        assert len(param.name) == 128

        # Should fail with 129 chars
        with pytest.raises(ValidationError):
            QueryParameter(name="a" * 129, value=1)


class TestQueryRequest:
    """Tests for QueryRequest model."""

    def test_valid_request(self) -> None:
        """Test creating valid query request."""
        request = QueryRequest(
            sql="SELECT * FROM users WHERE id = 1",
        )
        assert "SELECT" in request.sql
        assert request.timeout_seconds == 60  # default

    def test_sql_stripped(self) -> None:
        """Test that SQL is stripped of whitespace."""
        request = QueryRequest(sql="  SELECT * FROM users  ")
        assert request.sql == "SELECT * FROM users"

    def test_sql_semicolon_removed(self) -> None:
        """Test that trailing semicolons are removed."""
        request = QueryRequest(sql="SELECT * FROM users;")
        assert not request.sql.endswith(";")

    def test_must_start_with_select(self) -> None:
        """Test that SQL must start with SELECT."""
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(sql="UPDATE users SET name = 'test'")
        assert "SELECT" in str(exc_info.value)

    def test_allows_with_clause(self) -> None:
        """Test that WITH clause (CTE) is allowed."""
        request = QueryRequest(sql="WITH cte AS (SELECT 1) SELECT * FROM cte")
        assert request.sql.startswith("WITH")

    def test_blocks_drop_statement(self) -> None:
        """Test that DROP is blocked at model level."""
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(sql="SELECT 1; DROP TABLE users")
        assert "DROP" in str(exc_info.value).upper()

    def test_blocks_delete_statement(self) -> None:
        """Test that DELETE is blocked."""
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(sql="DELETE FROM users WHERE 1=1")
        assert "DELETE" in str(exc_info.value).upper()

    def test_empty_sql_rejected(self) -> None:
        """Test that empty SQL is rejected."""
        with pytest.raises(ValidationError):
            QueryRequest(sql="")

    def test_sql_max_length(self) -> None:
        """Test SQL max length validation."""
        # Should fail with SQL exceeding 100000 chars
        long_sql = "SELECT " + "a," * 50000 + "b FROM test"
        with pytest.raises(ValidationError):
            QueryRequest(sql=long_sql)

    def test_timeout_validation(self) -> None:
        """Test timeout value validation."""
        # Valid timeout
        request = QueryRequest(sql="SELECT 1", timeout_seconds=300)
        assert request.timeout_seconds == 300

        # Timeout too low
        with pytest.raises(ValidationError):
            QueryRequest(sql="SELECT 1", timeout_seconds=0)

        # Timeout too high (max 300 seconds for sync queries)
        with pytest.raises(ValidationError):
            QueryRequest(sql="SELECT 1", timeout_seconds=301)

    def test_parameters_list(self) -> None:
        """Test query with parameters."""
        request = QueryRequest(
            sql="SELECT * FROM users WHERE id = :user_id",
            parameters=[
                QueryParameter(name="user_id", value=123),
            ],
        )
        assert len(request.parameters) == 1
        assert request.parameters[0].name == "user_id"

    def test_default_timeout(self) -> None:
        """Test default timeout value."""
        request = QueryRequest(sql="SELECT 1")
        assert request.timeout_seconds == 60

    def test_idempotency_key(self) -> None:
        """Test idempotency key field."""
        request = QueryRequest(
            sql="SELECT 1",
            idempotency_key="unique-key-123",
        )
        assert request.idempotency_key == "unique-key-123"

    def test_idempotency_key_max_length(self) -> None:
        """Test idempotency key max length."""
        # Should work with 128 chars
        request = QueryRequest(sql="SELECT 1", idempotency_key="a" * 128)
        assert len(request.idempotency_key) == 128

        # Should fail with 129 chars
        with pytest.raises(ValidationError):
            QueryRequest(sql="SELECT 1", idempotency_key="a" * 129)

    def test_metadata_field(self) -> None:
        """Test custom metadata field."""
        request = QueryRequest(
            sql="SELECT 1",
            metadata={"source": "dashboard", "report_id": "r-123"},
        )
        assert request.metadata == {"source": "dashboard", "report_id": "r-123"}

    def test_metadata_none_by_default(self) -> None:
        """Test metadata is None by default."""
        request = QueryRequest(sql="SELECT 1")
        assert request.metadata is None

    def test_timeout_boundary_values(self) -> None:
        """Test timeout boundary values."""
        # Minimum (1 second)
        request = QueryRequest(sql="SELECT 1", timeout_seconds=1)
        assert request.timeout_seconds == 1

        # Maximum (300 seconds for sync)
        request = QueryRequest(sql="SELECT 1", timeout_seconds=300)
        assert request.timeout_seconds == 300

    def test_sql_with_newlines(self) -> None:
        """Test SQL with newlines is accepted."""
        sql = """
        SELECT
            id,
            name
        FROM users
        WHERE status = 'active'
        """
        request = QueryRequest(sql=sql)
        assert "SELECT" in request.sql

    def test_sql_with_comments(self) -> None:
        """Test SQL with comments."""
        sql = "SELECT * FROM users -- get all users"
        request = QueryRequest(sql=sql)
        assert "users" in request.sql


class TestResultMetadata:
    """Tests for ResultMetadata model."""

    def test_basic_metadata(self) -> None:
        """Test creating basic result metadata."""
        metadata = ResultMetadata(
            columns=[{"name": "id", "type": "int4"}],
            row_count=100,
        )
        assert metadata.row_count == 100
        assert metadata.truncated is False
        assert metadata.message is None

    def test_truncated_metadata(self) -> None:
        """Test metadata with truncation flag."""
        metadata = ResultMetadata(
            columns=[{"name": "id", "type": "int4"}],
            row_count=10000,
            truncated=True,
            message="Result exceeds limit. Use bulk API.",
        )
        assert metadata.truncated is True
        assert "bulk" in metadata.message.lower()

    def test_execution_time(self) -> None:
        """Test metadata with execution time."""
        metadata = ResultMetadata(
            columns=[],
            row_count=0,
            execution_time_ms=250,
        )
        assert metadata.execution_time_ms == 250

    def test_zero_row_count(self) -> None:
        """Test metadata with zero rows."""
        metadata = ResultMetadata(
            columns=[{"name": "id", "type": "int4"}],
            row_count=0,
        )
        assert metadata.row_count == 0

    def test_multiple_columns(self) -> None:
        """Test metadata with multiple columns."""
        metadata = ResultMetadata(
            columns=[
                {"name": "id", "type": "int4"},
                {"name": "name", "type": "varchar"},
                {"name": "amount", "type": "numeric"},
                {"name": "created_at", "type": "timestamp"},
            ],
            row_count=50,
        )
        assert len(metadata.columns) == 4


class TestQueryResponse:
    """Tests for QueryResponse model."""

    def test_valid_response(self) -> None:
        """Test creating valid response."""
        response = QueryResponse(
            job_id="job-123",
            status="COMPLETED",
        )
        assert response.job_id == "job-123"
        assert response.status == "COMPLETED"

    def test_response_with_data(self) -> None:
        """Test response with inline data."""
        from spectra.models.query import ResultMetadata

        response = QueryResponse(
            job_id="job-123",
            status="COMPLETED",
            data=[{"id": 1}, {"id": 2}],
            metadata=ResultMetadata(
                columns=[{"name": "id", "type": "int4"}],
                row_count=2,
                truncated=False,
            ),
        )
        assert len(response.data) == 2
        assert response.metadata.row_count == 2
        assert response.metadata.truncated is False

    def test_response_with_truncation(self) -> None:
        """Test response with truncated results."""
        from spectra.models.query import ResultMetadata

        response = QueryResponse(
            job_id="job-123",
            status="COMPLETED",
            data=[{"id": i} for i in range(100)],
            metadata=ResultMetadata(
                columns=[{"name": "id", "type": "int4"}],
                row_count=100,
                truncated=True,
                message="Result exceeds limit. Use bulk API.",
            ),
        )
        assert response.metadata.truncated is True
        assert "bulk" in response.metadata.message.lower()

    def test_response_with_error(self) -> None:
        """Test response with error."""
        response = QueryResponse(
            job_id="job-123",
            status="FAILED",
            error={"code": "QUERY_FAILED", "message": "Syntax error"},
        )
        assert response.status == "FAILED"
        assert response.error["code"] == "QUERY_FAILED"

    def test_response_serialization(self) -> None:
        """Test response serialization to JSON."""
        response = QueryResponse(
            job_id="job-123",
            status="COMPLETED",
            data=[{"id": 1}],
            metadata=ResultMetadata(
                columns=[{"name": "id", "type": "int4"}],
                row_count=1,
                execution_time_ms=150,
            ),
        )
        data = response.model_dump(mode="json")
        assert data["job_id"] == "job-123"
        assert data["metadata"]["execution_time_ms"] == 150

    def test_response_timeout_status(self) -> None:
        """Test response with TIMEOUT status."""
        response = QueryResponse(
            job_id="job-timeout",
            status="TIMEOUT",
            error={
                "code": "QUERY_TIMEOUT",
                "message": "Query exceeded 300 seconds. Use bulk API.",
            },
        )
        assert response.status == "TIMEOUT"
        assert response.error["code"] == "QUERY_TIMEOUT"
        assert response.data is None

    def test_response_all_statuses(self) -> None:
        """Test all valid response statuses."""
        for status in ["COMPLETED", "FAILED", "TIMEOUT"]:
            response = QueryResponse(job_id="job-123", status=status)
            assert response.status == status

    def test_response_with_empty_data(self) -> None:
        """Test response with empty data array."""
        response = QueryResponse(
            job_id="job-empty",
            status="COMPLETED",
            data=[],
            metadata=ResultMetadata(
                columns=[{"name": "id", "type": "int4"}],
                row_count=0,
            ),
        )
        assert response.data == []
        assert response.metadata.row_count == 0

    def test_response_with_complex_data_types(self) -> None:
        """Test response with various data types."""
        response = QueryResponse(
            job_id="job-complex",
            status="COMPLETED",
            data=[
                {
                    "id": 1,
                    "name": "Test",
                    "amount": 99.99,
                    "active": True,
                    "created_at": "2024-01-01T00:00:00Z",
                    "tags": ["a", "b"],
                    "metadata": {"key": "value"},
                }
            ],
            metadata=ResultMetadata(
                columns=[
                    {"name": "id", "type": "int4"},
                    {"name": "name", "type": "varchar"},
                    {"name": "amount", "type": "numeric"},
                    {"name": "active", "type": "bool"},
                    {"name": "created_at", "type": "timestamp"},
                    {"name": "tags", "type": "super"},
                    {"name": "metadata", "type": "super"},
                ],
                row_count=1,
            ),
        )
        assert response.data[0]["amount"] == 99.99
        assert response.data[0]["active"] is True


class TestBulkQueryItem:
    """Tests for BulkQueryItem model."""

    def test_valid_bulk_item(self) -> None:
        """Test creating valid bulk query item."""
        item = BulkQueryItem(
            id="query-1",
            sql="SELECT * FROM orders WHERE date = '2024-01-01'",
        )
        assert item.id == "query-1"
        assert "SELECT" in item.sql

    def test_with_priority(self) -> None:
        """Test bulk item with priority."""
        item = BulkQueryItem(
            id="urgent-query",
            sql="SELECT 1",
            priority=100,
        )
        assert item.priority == 100

    def test_id_max_length(self) -> None:
        """Test ID max length validation."""
        with pytest.raises(ValidationError):
            BulkQueryItem(id="a" * 65, sql="SELECT 1")

    def test_with_parameters(self) -> None:
        """Test bulk item with parameters."""
        item = BulkQueryItem(
            id="q1",
            sql="SELECT * FROM users WHERE id = :id",
            parameters=[QueryParameter(name="id", value=123)],
        )
        assert len(item.parameters) == 1
