"""Unit tests for Query Lambda handler.

Tests cover:
- Query submission
- Request/response validation
- Error handling
- Tenant context extraction
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from spectra.models.job import Job, JobStatus


def create_query_event(
    body: dict | None = None,
    tenant_id: str = "tenant-123",
    db_user: str = "user_tenant_123",
) -> dict:
    """Create a mock API Gateway event for query endpoint."""
    default_body = {
        "sql": "SELECT * FROM users LIMIT 100",
        "output_format": "json",
        "async": True,
    }
    return {
        "httpMethod": "POST",
        "path": "/v1/queries",
        "resource": "/v1/queries",
        "headers": {
            "Content-Type": "application/json",
            "X-Tenant-ID": tenant_id,
            "X-DB-User": db_user,
        },
        "body": json.dumps(body or default_body),
        "requestContext": {
            "requestId": "test-request-123",
            "identity": {"sourceIp": "127.0.0.1"},
            "stage": "test",
        },
        "pathParameters": {},
        "queryStringParameters": {},
        "isBase64Encoded": False,
    }


@pytest.fixture
def sample_job() -> Job:
    """Create a sample job for testing."""
    now = datetime.now(UTC)
    return Job(
        job_id="job-abc123def456",
        tenant_id="tenant-123",
        status=JobStatus.QUEUED,
        sql="SELECT * FROM test_table LIMIT 10",
        sql_hash="a1b2c3d4",
        db_user="user_tenant_123",
        db_group="analytics",
        created_at=now,
        updated_at=now,
        output_format="json",
        async_mode=True,
        timeout_seconds=900,
        ttl=int(now.timestamp()) + 86400 * 7,
    )


@pytest.fixture
def mock_context():
    """Create a mock Lambda context."""
    context = MagicMock()
    context.function_name = "spectra-query"
    context.aws_request_id = "req-123"
    context.memory_limit_in_mb = 128
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:spectra-query"
    return context


# =============================================================================
# Query Handler Tests
# =============================================================================


class TestQueryHandler:
    """Tests for query submission handler."""

    def test_submit_query_success(self, sample_job, mock_context):
        """Test successful query submission."""
        from spectra.handlers.query import app

        event = create_query_event()

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = "analytics"
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.JobService") as mock_job_svc:
                    mock_job_svc.return_value.create_job.return_value = sample_job

                    with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                        mock_rs.return_value.execute_statement.return_value = "stmt-123"

                        result = app.resolve(event, mock_context)

                        assert result["statusCode"] == 201
                        body = json.loads(result["body"])
                        assert body["job_id"] == sample_job.job_id

    def test_submit_query_unauthorized(self, mock_context):
        """Test query submission without tenant context."""
        from spectra.handlers.query import app

        event = create_query_event()

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            mock_ctx.side_effect = ValueError("Missing tenant context")

            result = app.resolve(event, mock_context)

            assert result["statusCode"] == 401

    def test_submit_query_missing_sql(self, mock_context):
        """Test query submission without SQL."""
        from spectra.handlers.query import app

        event = create_query_event(body={"output_format": "json"})

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            mock_ctx.return_value = ctx

            result = app.resolve(event, mock_context)

            assert result["statusCode"] == 400

    def test_submit_query_sql_validation_failure(self, mock_context):
        """Test query submission with SQL that fails validation."""
        from spectra.handlers.query import app
        from spectra.utils.sql_validator import SQLValidationError

        event = create_query_event(body={"sql": "DROP TABLE users", "output_format": "json"})

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.side_effect = SQLValidationError(
                    message="Forbidden statement: DROP",
                    error_code="FORBIDDEN_STATEMENT",
                )
                mock_validator.return_value = validator

                result = app.resolve(event, mock_context)

                assert result["statusCode"] == 400


class TestQueryHandlerIntegration:
    """Integration tests for Query Lambda handler with mocked AWS services."""

    def test_query_handler_full_flow(self, mock_dynamodb, mock_context, monkeypatch):
        """Test full query submission flow."""

        # Need to reimport handler after setting env var
        import importlib
        import spectra.handlers.query

        importlib.reload(spectra.handlers.query)
        from spectra.handlers.query import handler

        event = create_query_event()

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_val:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_val.return_value = validator

                with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                    mock_rs.return_value.execute_statement.return_value = "stmt-123"

                    with patch("spectra.handlers.query.JobService") as mock_job_svc:
                        now = datetime.now(UTC)
                        job = Job(
                            job_id="job-test",
                            tenant_id="tenant-123",
                            status=JobStatus.QUEUED,
                            sql="SELECT * FROM users",
                            sql_hash="hash",
                            db_user="user_tenant_123",
                            created_at=now,
                            updated_at=now,
                        )
                        mock_job_svc.return_value.create_job.return_value = job

                        result = handler(event, mock_context)

                        assert result["statusCode"] in [200, 201]
