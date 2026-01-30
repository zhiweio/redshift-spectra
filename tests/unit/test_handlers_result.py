"""Unit tests for Result Lambda handler.

Tests cover:
- Job result retrieval
- Pending job handling
- Completed job handling
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from spectra.models.job import Job, JobResult, JobStatus


def create_result_event(
    job_id: str = "job-123",
    tenant_id: str = "tenant-123",
) -> dict:
    """Create a mock API Gateway event for result endpoint."""
    return {
        "httpMethod": "GET",
        "path": f"/v1/jobs/{job_id}/results",
        "resource": "/v1/jobs/{job_id}/results",
        "headers": {
            "Content-Type": "application/json",
            "X-Tenant-ID": tenant_id,
        },
        "body": None,
        "requestContext": {
            "requestId": "test-request-123",
            "identity": {"sourceIp": "127.0.0.1"},
            "stage": "test",
        },
        "pathParameters": {"job_id": job_id},
        "queryStringParameters": {},
        "isBase64Encoded": False,
    }


@pytest.fixture
def mock_context():
    """Create a mock Lambda context."""
    context = MagicMock()
    context.function_name = "spectra-result"
    context.aws_request_id = "req-123"
    context.memory_limit_in_mb = 128
    return context


# =============================================================================
# Result Handler Tests
# =============================================================================


class TestResultHandler:
    """Tests for job result handler."""

    def test_get_result_running_job(self, mock_context):
        """Test getting result for running job returns error."""
        from spectra.handlers.result import app

        now = datetime.now(UTC)
        job = Job(
            job_id="job-123",
            tenant_id="tenant-123",
            status=JobStatus.RUNNING,
            sql="SELECT 1",
            sql_hash="abc",
            db_user="user",
            created_at=now,
            updated_at=now,
            output_format="json",
            async_mode=True,
            timeout_seconds=900,
            ttl=int(now.timestamp()) + 86400,
        )

        event = create_result_event(job_id="job-123")

        with patch("spectra.handlers.result.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.result.JobService") as mock_svc:
                mock_svc.return_value.get_job.return_value = job

                result = app.resolve(event, mock_context)

                # Running job should return 400 (not completed)
                assert result["statusCode"] == 400

    def test_get_result_completed_job(self, mock_context):
        """Test getting result for completed job."""
        from spectra.handlers.result import app

        now = datetime.now(UTC)
        job = Job(
            job_id="job-123",
            tenant_id="tenant-123",
            status=JobStatus.COMPLETED,
            sql="SELECT 1",
            sql_hash="abc",
            db_user="user",
            created_at=now,
            updated_at=now,
            completed_at=now,
            output_format="json",
            async_mode=True,
            timeout_seconds=900,
            ttl=int(now.timestamp()) + 86400,
            statement_id="stmt-123",  # Required for fetching results from Redshift
            result=JobResult(
                row_count=10,
                size_bytes=500,
                location="inline",
                columns=["id"],
                column_types=["integer"],
            ),
        )

        event = create_result_event(job_id="job-123")

        with patch("spectra.handlers.result.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.result.JobService") as mock_svc:
                mock_svc.return_value.get_job.return_value = job

                with (
                    patch("spectra.handlers.result.ExportService"),
                    patch("spectra.handlers.result.RedshiftService") as mock_rs,
                ):
                    # Mock Redshift result for inline mode (with pagination support)
                    mock_rs.return_value.get_all_statement_results.return_value = {
                        "total_rows": 10,
                        "columns": [{"name": "id", "type": "integer"}],
                        "records": [{"id": 1}, {"id": 2}],
                        "format": "CSV",
                        "pages_fetched": 1,
                    }
                    result = app.resolve(event, mock_context)

                    assert result["statusCode"] == 200

    def test_get_result_failed_job(self, mock_context):
        """Test getting result for failed job returns error info."""
        from spectra.handlers.result import app
        from spectra.models.job import JobError

        now = datetime.now(UTC)
        job = Job(
            job_id="job-123",
            tenant_id="tenant-123",
            status=JobStatus.FAILED,
            sql="SELECT 1",
            sql_hash="abc",
            db_user="user",
            created_at=now,
            updated_at=now,
            output_format="json",
            async_mode=True,
            timeout_seconds=900,
            ttl=int(now.timestamp()) + 86400,
            error=JobError(code="QUERY_ERROR", message="Syntax error"),
        )

        event = create_result_event(job_id="job-123")

        with patch("spectra.handlers.result.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.result.JobService") as mock_svc:
                mock_svc.return_value.get_job.return_value = job

                result = app.resolve(event, mock_context)

                assert result["statusCode"] == 200
                body = json.loads(result["body"])
                assert body["status"] == "FAILED"
                assert "error" in body
