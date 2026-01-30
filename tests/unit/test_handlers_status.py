"""Unit tests for Status Lambda handler.

Tests cover:
- Job status retrieval
- Not found handling
- Tenant context extraction
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from spectra.models.job import Job, JobStatus


def create_status_event(
    job_id: str = "job-123",
    tenant_id: str = "tenant-123",
) -> dict:
    """Create a mock API Gateway event for status endpoint."""
    return {
        "httpMethod": "GET",
        "path": f"/v1/jobs/{job_id}",
        "resource": "/v1/jobs/{job_id}",
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
    context.function_name = "spectra-status"
    context.aws_request_id = "req-123"
    context.memory_limit_in_mb = 128
    return context


# =============================================================================
# Status Handler Tests
# =============================================================================


class TestStatusHandler:
    """Tests for job status handler."""

    def test_get_job_status_success(self, mock_context):
        """Test getting job status successfully."""
        from spectra.handlers.status import app

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

        event = create_status_event(job_id="job-123")

        with patch("spectra.handlers.status.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.status.JobService") as mock_svc:
                mock_svc.return_value.get_job.return_value = job
                mock_svc.return_value.sync_job_status.return_value = job

                result = app.resolve(event, mock_context)

                assert result["statusCode"] == 200
                body = json.loads(result["body"])
                assert body["job_id"] == "job-123"
                assert body["status"] == "RUNNING"

    def test_get_job_status_not_found(self, mock_context):
        """Test getting status for non-existent job."""
        from spectra.handlers.status import app
        from spectra.services.job import JobNotFoundError

        event = create_status_event(job_id="job-nonexistent")

        with patch("spectra.handlers.status.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.status.JobService") as mock_svc:
                mock_svc.return_value.get_job.side_effect = JobNotFoundError("Job not found")

                result = app.resolve(event, mock_context)

                assert result["statusCode"] == 404
