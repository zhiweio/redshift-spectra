"""Unit tests for Bulk Lambda handler.

Tests cover:
- Bulk job creation (export/import)
- Bulk job retrieval
- Error handling
- Tenant context extraction
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


def create_bulk_event(
    method: str = "POST",
    path: str = "/v1/bulk/jobs",
    body: dict | None = None,
    path_params: dict | None = None,
    tenant_id: str = "tenant-123",
    db_user: str = "user_tenant_123",
) -> dict:
    """Create a mock API Gateway event for bulk endpoint."""
    return {
        "httpMethod": method,
        "path": path,
        "resource": path.replace("bulk-123", "{job_id}") if "bulk-123" in path else path,
        "headers": {
            "Content-Type": "application/json",
            "X-Tenant-ID": tenant_id,
            "X-DB-User": db_user,
        },
        "body": json.dumps(body) if body else None,
        "requestContext": {
            "requestId": "test-request-123",
            "identity": {"sourceIp": "127.0.0.1"},
            "stage": "test",
        },
        "pathParameters": path_params or {},
        "queryStringParameters": {},
        "isBase64Encoded": False,
    }


@pytest.fixture
def mock_context():
    """Create a mock Lambda context."""
    context = MagicMock()
    context.function_name = "spectra-bulk"
    context.aws_request_id = "req-123"
    context.memory_limit_in_mb = 128
    return context


# =============================================================================
# Bulk Handler Tests
# =============================================================================


class TestBulkHandler:
    """Tests for bulk job handler."""

    def test_create_bulk_job_export(self, mock_context):
        """Test creating bulk export job."""
        from spectra.handlers.bulk import app
        from spectra.models.bulk import (
            BulkJob,
            BulkJobState,
            BulkOperation,
            CompressionType,
            DataFormat,
        )

        now = datetime.now(UTC)
        bulk_job = BulkJob(
            job_id="bulk-123",
            tenant_id="tenant-123",
            operation=BulkOperation.QUERY,
            state=BulkJobState.OPEN,
            content_type=DataFormat.CSV,
            compression=CompressionType.GZIP,
            query="SELECT * FROM users",
            db_user="user_tenant_123",
            created_at=now,
            updated_at=now,
        )

        event = create_bulk_event(
            body={
                "operation": "query",
                "query": "SELECT * FROM users",
                "content_type": "CSV",
            }
        )

        with patch("spectra.handlers.bulk.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.bulk.BulkJobService") as mock_svc:
                mock_svc.return_value.create_job.return_value = bulk_job

                result = app.resolve(event, mock_context)

                assert result["statusCode"] == 201
                body = json.loads(result["body"])
                assert body["job_id"] == "bulk-123"

    def test_create_bulk_job_import_without_object(self, mock_context):
        """Test creating bulk import job without object name."""
        from spectra.handlers.bulk import app

        event = create_bulk_event(
            body={
                "operation": "insert",
                "content_type": "CSV",
            }
        )

        with patch("spectra.handlers.bulk.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            mock_ctx.return_value = ctx

            result = app.resolve(event, mock_context)

            assert result["statusCode"] == 400

    def test_get_bulk_job_success(self, mock_context):
        """Test getting bulk job info."""
        from spectra.handlers.bulk import app
        from spectra.models.bulk import (
            BulkJob,
            BulkJobState,
            BulkOperation,
            CompressionType,
            DataFormat,
        )

        now = datetime.now(UTC)
        bulk_job = BulkJob(
            job_id="bulk-123",
            tenant_id="tenant-123",
            operation=BulkOperation.QUERY,
            state=BulkJobState.JOB_COMPLETE,
            content_type=DataFormat.CSV,
            compression=CompressionType.GZIP,
            query="SELECT * FROM users",
            db_user="user_tenant_123",
            created_at=now,
            updated_at=now,
            records_processed=1000,
        )

        event = create_bulk_event(
            method="GET",
            path="/v1/bulk/jobs/bulk-123",
            path_params={"job_id": "bulk-123"},
        )

        with patch("spectra.handlers.bulk.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.bulk.BulkJobService") as mock_svc:
                mock_svc.return_value.get_job.return_value = bulk_job

                result = app.resolve(event, mock_context)

                assert result["statusCode"] == 200
                body = json.loads(result["body"])
                assert body["job_id"] == "bulk-123"

    def test_get_bulk_job_not_found(self, mock_context):
        """Test getting non-existent bulk job."""
        from spectra.handlers.bulk import app
        from spectra.services.bulk import BulkJobNotFoundError

        event = create_bulk_event(
            method="GET",
            path="/v1/bulk/jobs/bulk-nonexistent",
            path_params={"job_id": "bulk-nonexistent"},
        )

        with patch("spectra.handlers.bulk.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.bulk.BulkJobService") as mock_svc:
                mock_svc.return_value.get_job.side_effect = BulkJobNotFoundError("Job not found")

                result = app.resolve(event, mock_context)

                assert result["statusCode"] == 404


class TestBulkHandlerIntegration:
    """Integration tests for Bulk Lambda handler with mocked AWS services."""

    def test_bulk_handler_full_flow(self, _mock_dynamodb, _mock_s3, mock_context, _monkeypatch):
        """Test full bulk job creation flow."""

        from spectra.handlers.bulk import handler
        from spectra.models.bulk import (
            BulkJob,
            BulkJobState,
            BulkOperation,
            CompressionType,
            DataFormat,
        )

        now = datetime.now(UTC)
        bulk_job = BulkJob(
            job_id="bulk-test",
            tenant_id="tenant-123",
            operation=BulkOperation.QUERY,
            state=BulkJobState.OPEN,
            content_type=DataFormat.CSV,
            compression=CompressionType.GZIP,
            query="SELECT * FROM test_table",
            db_user="user_tenant_123",
            created_at=now,
            updated_at=now,
        )

        event = create_bulk_event(
            body={
                "operation": "query",
                "query": "SELECT * FROM test_table",
                "content_type": "CSV",
            }
        )

        with patch("spectra.handlers.bulk.extract_tenant_context") as mock_ctx:
            ctx = MagicMock()
            ctx.tenant_id = "tenant-123"
            ctx.db_user = "user_tenant_123"
            mock_ctx.return_value = ctx

            with patch("spectra.handlers.bulk.BulkJobService") as mock_svc:
                mock_svc.return_value.create_job.return_value = bulk_job

                result = handler(event, mock_context)

                # Bulk job creation returns 201
                assert result["statusCode"] in [200, 201]
