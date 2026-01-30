"""Unit tests for query models.

Tests cover:
- QueryParameter validation
- QueryRequest validation
- QueryResponse serialization
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
            output_format=OutputFormat.JSON,
        )
        assert "SELECT" in request.sql
        assert request.output_format == OutputFormat.JSON
        assert request.async_mode is True  # default

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

        # Timeout too high
        with pytest.raises(ValidationError):
            QueryRequest(sql="SELECT 1", timeout_seconds=86401)

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

    def test_output_formats(self) -> None:
        """Test all output format options."""
        for fmt in OutputFormat:
            request = QueryRequest(sql="SELECT 1", output_format=fmt)
            assert request.output_format == fmt

    def test_async_alias(self) -> None:
        """Test that 'async' alias works."""
        # Using model_validate to test alias
        data = {"sql": "SELECT 1", "async": False}
        request = QueryRequest.model_validate(data)
        assert request.async_mode is False


class TestQueryResponse:
    """Tests for QueryResponse model."""

    def test_valid_response(self) -> None:
        """Test creating valid response."""
        now = datetime.now(UTC)
        response = QueryResponse(
            job_id="job-123",
            status="QUEUED",
            submitted_at=now,
            tenant_id="tenant-456",
        )
        assert response.job_id == "job-123"
        assert response.status == "QUEUED"
        assert response.tenant_id == "tenant-456"

    def test_optional_fields(self) -> None:
        """Test optional fields default to None."""
        response = QueryResponse(
            job_id="job-123",
            status="QUEUED",
            submitted_at=datetime.now(UTC),
            tenant_id="tenant-456",
        )
        assert response.estimated_duration_seconds is None
        assert response.poll_url is None
        assert response.result_url is None

    def test_response_serialization(self) -> None:
        """Test response serialization to JSON."""
        now = datetime.now(UTC)
        response = QueryResponse(
            job_id="job-123",
            status="COMPLETED",
            submitted_at=now,
            tenant_id="tenant-456",
            estimated_duration_seconds=30,
        )
        data = response.model_dump(mode="json")
        assert data["job_id"] == "job-123"
        assert data["estimated_duration_seconds"] == 30
        assert isinstance(data["submitted_at"], str)


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
