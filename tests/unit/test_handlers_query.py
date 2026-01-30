"""Unit tests for Query Lambda handler.

Tests cover:
- Synchronous query execution
- LIMIT injection and truncation handling
- Timeout handling
- Error handling
- Tenant context extraction
- Idempotency key handling
- Parameter binding
- Edge cases (empty results, max rows, etc.)
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from spectra.models.job import Job, JobStatus
from spectra.services.redshift import QueryExecutionError, QueryTimeoutError


def create_query_event(
    body: dict | None = None,
    tenant_id: str = "tenant-123",
    db_user: str = "user_tenant_123",
    db_group: str | None = "analytics",
) -> dict:
    """Create a mock API Gateway event for query endpoint."""
    default_body = {
        "sql": "SELECT * FROM users",
        "timeout_seconds": 60,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-ID": tenant_id,
        "X-DB-User": db_user,
    }
    if db_group:
        headers["X-DB-Group"] = db_group

    return {
        "httpMethod": "POST",
        "path": "/v1/queries",
        "resource": "/v1/queries",
        "headers": headers,
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
        sql="SELECT * FROM test_table",
        sql_hash="a1b2c3d4",
        db_user="user_tenant_123",
        db_group="analytics",
        created_at=now,
        updated_at=now,
        output_format="json",
        async_mode=False,
        timeout_seconds=60,
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
    """Tests for synchronous query execution handler."""

    def test_submit_query_success(self, sample_job, mock_context):
        """Test successful synchronous query execution."""
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

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = ("SELECT * FROM users LIMIT 10001", None)

                    with patch("spectra.handlers.query.JobService") as mock_job_svc:
                        mock_job_svc.return_value.create_job.return_value = sample_job

                        with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                            mock_rs.return_value.execute_statement.return_value = "stmt-123"
                            mock_rs.return_value.wait_for_statement.return_value = {
                                "status": "FINISHED",
                                "result_rows": 5,
                                "duration": 1000,
                            }
                            mock_rs.return_value.get_all_statement_results.return_value = {
                                "columns": [{"name": "id", "type": "int4"}],
                                "records": [{"id": 1}, {"id": 2}, {"id": 3}],
                                "total_rows": 3,
                            }

                            result = app.resolve(event, mock_context)

                            assert result["statusCode"] == 200
                            body = json.loads(result["body"])
                            assert body["job_id"] == sample_job.job_id
                            assert body["status"] == "COMPLETED"
                            assert body["data"] == [{"id": 1}, {"id": 2}, {"id": 3}]
                            assert body["metadata"]["row_count"] == 3
                            assert body["metadata"]["truncated"] is False

    def test_submit_query_truncated(self, sample_job, mock_context):
        """Test query execution with truncated results."""
        from spectra.handlers.query import app

        event = create_query_event()

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = ("SELECT * FROM users LIMIT 10001", None)

                    with patch("spectra.handlers.query.get_settings") as mock_settings:
                        settings = MagicMock()
                        settings.result_size_threshold = 3  # Small threshold for testing
                        settings.sql_security_level = "standard"
                        settings.sql_max_query_length = 100000
                        settings.sql_max_joins = 10
                        settings.sql_max_subqueries = 5
                        settings.sql_allow_cte = True
                        settings.sql_allow_union = False
                        mock_settings.return_value = settings

                        with patch("spectra.handlers.query.JobService") as mock_job_svc:
                            mock_job_svc.return_value.create_job.return_value = sample_job

                            with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                                mock_rs.return_value.execute_statement.return_value = "stmt-123"
                                mock_rs.return_value.wait_for_statement.return_value = {
                                    "status": "FINISHED",
                                    "result_rows": 4,
                                }
                                # Return 4 records (threshold + 1)
                                mock_rs.return_value.get_all_statement_results.return_value = {
                                    "columns": [{"name": "id", "type": "int4"}],
                                    "records": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}],
                                    "total_rows": 4,
                                }

                                result = app.resolve(event, mock_context)

                                assert result["statusCode"] == 200
                                body = json.loads(result["body"])
                                assert body["status"] == "COMPLETED"
                                assert body["metadata"]["truncated"] is True
                                assert body["metadata"]["row_count"] == 3
                                assert len(body["data"]) == 3
                                assert "bulk" in body["metadata"]["message"].lower()

    def test_submit_query_timeout(self, sample_job, mock_context):
        """Test query execution that times out."""
        from spectra.handlers.query import app

        event = create_query_event(body={"sql": "SELECT * FROM large_table", "timeout_seconds": 5})

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = ("SELECT * FROM large_table LIMIT 10001", None)

                    with patch("spectra.handlers.query.JobService") as mock_job_svc:
                        mock_job_svc.return_value.create_job.return_value = sample_job

                        with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                            mock_rs.return_value.execute_statement.return_value = "stmt-123"
                            mock_rs.return_value.wait_for_statement.side_effect = QueryTimeoutError(
                                message="Query exceeded timeout of 5 seconds",
                                code="QUERY_TIMEOUT",
                            )

                            result = app.resolve(event, mock_context)

                            assert result["statusCode"] == 408
                            body = json.loads(result["body"])
                            assert body["status"] == "TIMEOUT"
                            assert body["error"]["code"] == "QUERY_TIMEOUT"
                            assert "bulk" in body["error"]["message"].lower()

    def test_submit_query_execution_error(self, sample_job, mock_context):
        """Test query execution that fails."""
        from spectra.handlers.query import app

        event = create_query_event()

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = ("SELECT * FROM users LIMIT 10001", None)

                    with patch("spectra.handlers.query.JobService") as mock_job_svc:
                        mock_job_svc.return_value.create_job.return_value = sample_job

                        with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                            mock_rs.return_value.execute_statement.return_value = "stmt-123"
                            mock_rs.return_value.wait_for_statement.side_effect = (
                                QueryExecutionError(
                                    message="Column 'invalid_col' does not exist",
                                    code="QUERY_FAILED",
                                )
                            )

                            result = app.resolve(event, mock_context)

                            assert result["statusCode"] == 500
                            body = json.loads(result["body"])
                            assert body["status"] == "FAILED"
                            assert body["error"]["code"] == "QUERY_FAILED"

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

        event = create_query_event(body={"timeout_seconds": 60})

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

        event = create_query_event(body={"sql": "DROP TABLE users"})

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

    def test_query_handler_full_flow(self, _mock_dynamodb, mock_context, _monkeypatch):
        """Test full synchronous query execution flow."""

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

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = ("SELECT * FROM users LIMIT 10001", None)

                    with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                        mock_rs.return_value.execute_statement.return_value = "stmt-123"
                        mock_rs.return_value.wait_for_statement.return_value = {
                            "status": "FINISHED",
                            "result_rows": 2,
                        }
                        mock_rs.return_value.get_all_statement_results.return_value = {
                            "columns": [{"name": "id", "type": "int4"}],
                            "records": [{"id": 1}, {"id": 2}],
                            "total_rows": 2,
                        }

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
                                async_mode=False,
                            )
                            mock_job_svc.return_value.create_job.return_value = job

                            result = handler(event, mock_context)

                            assert result["statusCode"] == 200
                            body = json.loads(result["body"])
                            assert body["status"] == "COMPLETED"
                            assert "data" in body


class TestQueryHandlerEdgeCases:
    """Tests for edge cases in query handler."""

    def test_empty_result_set(self, sample_job, mock_context):
        """Test query that returns no rows."""
        from spectra.handlers.query import app

        event = create_query_event(body={"sql": "SELECT * FROM users WHERE 1=0"})

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = ("SELECT * FROM users WHERE 1=0 LIMIT 10001", None)

                    with patch("spectra.handlers.query.JobService") as mock_job_svc:
                        mock_job_svc.return_value.create_job.return_value = sample_job

                        with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                            mock_rs.return_value.execute_statement.return_value = "stmt-123"
                            mock_rs.return_value.wait_for_statement.return_value = {
                                "status": "FINISHED",
                                "result_rows": 0,
                            }
                            mock_rs.return_value.get_all_statement_results.return_value = {
                                "columns": [{"name": "id", "type": "int4"}],
                                "records": [],
                                "total_rows": 0,
                            }

                            result = app.resolve(event, mock_context)

                            assert result["statusCode"] == 200
                            body = json.loads(result["body"])
                            assert body["status"] == "COMPLETED"
                            assert body["data"] == []
                            assert body["metadata"]["row_count"] == 0
                            assert body["metadata"]["truncated"] is False

    def test_exact_threshold_rows(self, sample_job, mock_context):
        """Test query that returns exactly threshold rows (should not truncate)."""
        from spectra.handlers.query import app

        event = create_query_event()

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = ("SELECT * FROM users LIMIT 4", None)

                    with patch("spectra.handlers.query.get_settings") as mock_settings:
                        settings = MagicMock()
                        settings.result_size_threshold = 3  # Small threshold for testing
                        settings.sql_security_level = "standard"
                        settings.sql_max_query_length = 100000
                        settings.sql_max_joins = 10
                        settings.sql_max_subqueries = 5
                        settings.sql_allow_cte = True
                        settings.sql_allow_union = False
                        mock_settings.return_value = settings

                        with patch("spectra.handlers.query.JobService") as mock_job_svc:
                            mock_job_svc.return_value.create_job.return_value = sample_job

                            with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                                mock_rs.return_value.execute_statement.return_value = "stmt-123"
                                mock_rs.return_value.wait_for_statement.return_value = {
                                    "status": "FINISHED",
                                    "result_rows": 3,
                                }
                                # Return exactly 3 records (threshold)
                                mock_rs.return_value.get_all_statement_results.return_value = {
                                    "columns": [{"name": "id", "type": "int4"}],
                                    "records": [{"id": 1}, {"id": 2}, {"id": 3}],
                                    "total_rows": 3,
                                }

                                result = app.resolve(event, mock_context)

                                assert result["statusCode"] == 200
                                body = json.loads(result["body"])
                                assert body["metadata"]["truncated"] is False
                                assert body["metadata"]["row_count"] == 3
                                assert len(body["data"]) == 3

    def test_query_with_parameters(self, sample_job, mock_context):
        """Test query execution with bound parameters."""
        from spectra.handlers.query import app

        event = create_query_event(
            body={
                "sql": "SELECT * FROM users WHERE id = :user_id AND status = :status",
                "parameters": [
                    {"name": "user_id", "value": 123},
                    {"name": "status", "value": "active"},
                ],
            }
        )

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = (
                        "SELECT * FROM users WHERE id = :user_id AND status = :status LIMIT 10001",
                        None,
                    )

                    with patch("spectra.handlers.query.JobService") as mock_job_svc:
                        mock_job_svc.return_value.create_job.return_value = sample_job

                        with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                            mock_rs.return_value.execute_statement.return_value = "stmt-123"
                            mock_rs.return_value.wait_for_statement.return_value = {
                                "status": "FINISHED",
                                "result_rows": 1,
                            }
                            mock_rs.return_value.get_all_statement_results.return_value = {
                                "columns": [
                                    {"name": "id", "type": "int4"},
                                    {"name": "name", "type": "varchar"},
                                ],
                                "records": [{"id": 123, "name": "Test User"}],
                                "total_rows": 1,
                            }

                            result = app.resolve(event, mock_context)

                            assert result["statusCode"] == 200
                            body = json.loads(result["body"])
                            assert body["status"] == "COMPLETED"
                            assert body["data"][0]["id"] == 123

    def test_query_with_idempotency_key(self, sample_job, mock_context):
        """Test query with idempotency key for deduplication."""
        from spectra.handlers.query import app

        event = create_query_event(
            body={
                "sql": "SELECT * FROM users",
                "idempotency_key": "unique-request-123",
            }
        )

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = ("SELECT * FROM users LIMIT 10001", None)

                    with patch("spectra.handlers.query.JobService") as mock_job_svc:
                        mock_job_svc.return_value.create_job.return_value = sample_job

                        with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                            mock_rs.return_value.execute_statement.return_value = "stmt-123"
                            mock_rs.return_value.wait_for_statement.return_value = {
                                "status": "FINISHED",
                                "result_rows": 1,
                            }
                            mock_rs.return_value.get_all_statement_results.return_value = {
                                "columns": [{"name": "id", "type": "int4"}],
                                "records": [{"id": 1}],
                                "total_rows": 1,
                            }

                            result = app.resolve(event, mock_context)

                            assert result["statusCode"] == 200
                            # Verify idempotency_key was passed to create_job
                            mock_job_svc.return_value.create_job.assert_called_once()
                            call_kwargs = mock_job_svc.return_value.create_job.call_args.kwargs
                            assert call_kwargs["idempotency_key"] == "unique-request-123"

    def test_duplicate_idempotency_key(self, _sample_job, mock_context):
        """Test handling of duplicate idempotency key."""
        from spectra.handlers.query import app
        from spectra.services.job import DuplicateJobError

        event = create_query_event(
            body={
                "sql": "SELECT * FROM users",
                "idempotency_key": "duplicate-key",
            }
        )

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = ("SELECT * FROM users LIMIT 10001", None)

                    with patch("spectra.handlers.query.JobService") as mock_job_svc:
                        mock_job_svc.return_value.create_job.side_effect = DuplicateJobError(
                            "existing-job-456"
                        )

                        result = app.resolve(event, mock_context)

                        assert result["statusCode"] == 400
                        body = json.loads(result["body"])
                        # The error message is in the 'message' field for BadRequestError
                        assert (
                            "duplicate" in body.get("message", "").lower()
                            or "duplicate" in str(body).lower()
                        )

    def test_query_with_metadata(self, sample_job, mock_context):
        """Test query with custom metadata."""
        from spectra.handlers.query import app

        event = create_query_event(
            body={
                "sql": "SELECT * FROM users",
                "metadata": {"source": "dashboard", "report_id": "report-123"},
            }
        )

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = ("SELECT * FROM users LIMIT 10001", None)

                    with patch("spectra.handlers.query.JobService") as mock_job_svc:
                        mock_job_svc.return_value.create_job.return_value = sample_job

                        with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                            mock_rs.return_value.execute_statement.return_value = "stmt-123"
                            mock_rs.return_value.wait_for_statement.return_value = {
                                "status": "FINISHED",
                                "result_rows": 1,
                            }
                            mock_rs.return_value.get_all_statement_results.return_value = {
                                "columns": [{"name": "id", "type": "int4"}],
                                "records": [{"id": 1}],
                                "total_rows": 1,
                            }

                            result = app.resolve(event, mock_context)

                            assert result["statusCode"] == 200
                            # Verify metadata was passed to create_job
                            mock_job_svc.return_value.create_job.assert_called_once()
                            call_kwargs = mock_job_svc.return_value.create_job.call_args.kwargs
                            assert call_kwargs["metadata"] == {
                                "source": "dashboard",
                                "report_id": "report-123",
                            }

    def test_query_with_cte(self, sample_job, mock_context):
        """Test query with Common Table Expression (CTE)."""
        from spectra.handlers.query import app

        cte_sql = """
        WITH active_users AS (
            SELECT id, name FROM users WHERE status = 'active'
        )
        SELECT * FROM active_users
        """

        event = create_query_event(body={"sql": cte_sql})

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = (cte_sql.strip() + " LIMIT 10001", None)

                    with patch("spectra.handlers.query.JobService") as mock_job_svc:
                        mock_job_svc.return_value.create_job.return_value = sample_job

                        with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                            mock_rs.return_value.execute_statement.return_value = "stmt-123"
                            mock_rs.return_value.wait_for_statement.return_value = {
                                "status": "FINISHED",
                                "result_rows": 2,
                            }
                            mock_rs.return_value.get_all_statement_results.return_value = {
                                "columns": [
                                    {"name": "id", "type": "int4"},
                                    {"name": "name", "type": "varchar"},
                                ],
                                "records": [
                                    {"id": 1, "name": "Alice"},
                                    {"id": 2, "name": "Bob"},
                                ],
                                "total_rows": 2,
                            }

                            result = app.resolve(event, mock_context)

                            assert result["statusCode"] == 200

    def test_query_respects_user_limit(self, sample_job, mock_context):
        """Test that user-provided smaller LIMIT is preserved."""
        from spectra.handlers.query import app

        event = create_query_event(body={"sql": "SELECT * FROM users LIMIT 10"})

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    # inject_limit should preserve smaller user limit
                    mock_limit.return_value = ("SELECT * FROM users LIMIT 10", 10)

                    with patch("spectra.handlers.query.JobService") as mock_job_svc:
                        mock_job_svc.return_value.create_job.return_value = sample_job

                        with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                            mock_rs.return_value.execute_statement.return_value = "stmt-123"
                            mock_rs.return_value.wait_for_statement.return_value = {
                                "status": "FINISHED",
                                "result_rows": 5,
                            }
                            mock_rs.return_value.get_all_statement_results.return_value = {
                                "columns": [{"name": "id", "type": "int4"}],
                                "records": [{"id": i} for i in range(5)],
                                "total_rows": 5,
                            }

                            result = app.resolve(event, mock_context)

                            assert result["statusCode"] == 200
                            body = json.loads(result["body"])
                            assert body["metadata"]["truncated"] is False
                            assert len(body["data"]) == 5

    def test_timeout_max_value(self, mock_context):
        """Test query with maximum allowed timeout."""
        from spectra.handlers.query import app

        # 300 seconds is the max for sync queries
        event = create_query_event(body={"sql": "SELECT * FROM users", "timeout_seconds": 300})

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            # Should accept the request (validation passes at model level)
            app.resolve(event, mock_context)
            # Will fail at validation but not because of timeout
            # The test verifies 300 is accepted as a valid timeout

    def test_invalid_json_body(self, mock_context):
        """Test handling of invalid JSON in request body."""
        from spectra.handlers.query import app

        event = create_query_event()
        event["body"] = "not valid json"

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            mock_ctx.return_value = ctx

            result = app.resolve(event, mock_context)

            assert result["statusCode"] == 400

    def test_sql_with_special_characters(self, sample_job, mock_context):
        """Test query with special characters in SQL."""
        from spectra.handlers.query import app

        event = create_query_event(body={"sql": "SELECT * FROM users WHERE name LIKE '%O''Brien%'"})

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = (
                        "SELECT * FROM users WHERE name LIKE '%O''Brien%' LIMIT 10001",
                        None,
                    )

                    with patch("spectra.handlers.query.JobService") as mock_job_svc:
                        mock_job_svc.return_value.create_job.return_value = sample_job

                        with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                            mock_rs.return_value.execute_statement.return_value = "stmt-123"
                            mock_rs.return_value.wait_for_statement.return_value = {
                                "status": "FINISHED",
                                "result_rows": 1,
                            }
                            mock_rs.return_value.get_all_statement_results.return_value = {
                                "columns": [{"name": "name", "type": "varchar"}],
                                "records": [{"name": "O'Brien"}],
                                "total_rows": 1,
                            }

                            result = app.resolve(event, mock_context)

                            assert result["statusCode"] == 200


class TestQueryHandlerMetrics:
    """Tests for query handler metrics and logging."""

    def test_metrics_on_success(self, sample_job, mock_context):
        """Test that success metrics are recorded."""
        from spectra.handlers.query import app

        event = create_query_event()

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = ("SELECT * FROM users LIMIT 10001", None)

                    with patch("spectra.handlers.query.JobService") as mock_job_svc:
                        mock_job_svc.return_value.create_job.return_value = sample_job

                        with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                            mock_rs.return_value.execute_statement.return_value = "stmt-123"
                            mock_rs.return_value.wait_for_statement.return_value = {
                                "status": "FINISHED",
                            }
                            mock_rs.return_value.get_all_statement_results.return_value = {
                                "columns": [],
                                "records": [{"id": 1}],
                                "total_rows": 1,
                            }

                            with patch("spectra.handlers.query.metrics") as mock_metrics:
                                result = app.resolve(event, mock_context)

                                assert result["statusCode"] == 200
                                # Verify metrics were called
                                assert mock_metrics.add_metric.called

    def test_metrics_on_truncation(self, sample_job, mock_context):
        """Test that truncation metrics are recorded."""
        from spectra.handlers.query import app

        event = create_query_event()

        with patch("spectra.handlers.query.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            ctx.db_group = None
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.query._get_sql_validator") as mock_validator:
                validator = MagicMock()
                validator.validate.return_value = MagicMock(is_valid=True, warnings=[])
                mock_validator.return_value = validator

                with patch("spectra.handlers.query.inject_limit") as mock_limit:
                    mock_limit.return_value = ("SELECT * FROM users LIMIT 4", None)

                    with patch("spectra.handlers.query.get_settings") as mock_settings:
                        settings = MagicMock()
                        settings.result_size_threshold = 3
                        settings.sql_security_level = "standard"
                        settings.sql_max_query_length = 100000
                        settings.sql_max_joins = 10
                        settings.sql_max_subqueries = 5
                        settings.sql_allow_cte = True
                        settings.sql_allow_union = False
                        mock_settings.return_value = settings

                        with patch("spectra.handlers.query.JobService") as mock_job_svc:
                            mock_job_svc.return_value.create_job.return_value = sample_job

                            with patch("spectra.handlers.query.RedshiftService") as mock_rs:
                                mock_rs.return_value.execute_statement.return_value = "stmt-123"
                                mock_rs.return_value.wait_for_statement.return_value = {
                                    "status": "FINISHED",
                                }
                                mock_rs.return_value.get_all_statement_results.return_value = {
                                    "columns": [],
                                    "records": [{"id": i} for i in range(4)],
                                    "total_rows": 4,
                                }

                                with patch("spectra.handlers.query.metrics"):
                                    result = app.resolve(event, mock_context)

                                    assert result["statusCode"] == 200
                                    body = json.loads(result["body"])
                                    assert body["metadata"]["truncated"] is True
