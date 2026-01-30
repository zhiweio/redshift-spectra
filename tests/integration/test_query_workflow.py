"""Integration tests for the query workflow.

These tests verify the complete query submission and retrieval workflow
using mocked AWS services (DynamoDB, S3, Redshift Data API).
"""

import json
import os
from datetime import UTC, datetime
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws


# =============================================================================
# Integration Test Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def aws_credentials() -> None:
    """Set up mock AWS credentials."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def mock_aws_services(aws_credentials: None) -> Generator[dict[str, Any], None, None]:
    """Set up all mocked AWS services."""
    with mock_aws():
        # Create DynamoDB tables
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        # Jobs table
        jobs_table = dynamodb.create_table(
            TableName="spectra-jobs",
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "tenant_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "tenant-index",
                    "KeySchema": [{"AttributeName": "tenant_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Sessions table
        sessions_table = dynamodb.create_table(
            TableName="spectra-sessions",
            KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
                {"AttributeName": "tenant_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "gsi1-tenant",
                    "KeySchema": [{"AttributeName": "tenant_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Bulk jobs table
        bulk_table = dynamodb.create_table(
            TableName="spectra-bulk-jobs",
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "tenant_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "gsi1-tenant",
                    "KeySchema": [{"AttributeName": "tenant_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Create S3 bucket
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")

        yield {
            "dynamodb": dynamodb,
            "jobs_table": jobs_table,
            "sessions_table": sessions_table,
            "bulk_table": bulk_table,
            "s3": s3,
        }


# =============================================================================
# Query Workflow Integration Tests
# =============================================================================


class TestQueryWorkflowIntegration:
    """Integration tests for the complete query workflow."""

    @pytest.fixture
    def mock_redshift_client(self) -> MagicMock:
        """Create a mock Redshift Data API client."""
        mock = MagicMock()
        mock.execute_statement.return_value = {
            "Id": "stmt-integration-123",
            "SessionId": "session-integration-456",
        }
        mock.describe_statement.return_value = {
            "Id": "stmt-integration-123",
            "Status": "FINISHED",
            "HasResultSet": True,
            "ResultRows": 10,
            "ResultSize": 1024,
        }
        mock.get_statement_result.return_value = {
            "Records": [
                [{"longValue": 1}, {"stringValue": "Test"}],
                [{"longValue": 2}, {"stringValue": "Test 2"}],
            ],
            "ColumnMetadata": [
                {"name": "id", "typeName": "int4"},
                {"name": "name", "typeName": "varchar"},
            ],
        }
        return mock

    def test_submit_query_creates_job(
        self, mock_aws_services: dict[str, Any], mock_redshift_client: MagicMock
    ) -> None:
        """Test that submitting a query creates a job record."""
        from spectra.services.job import JobService
        from spectra.models.job import JobStatus

        with patch("boto3.client", return_value=mock_redshift_client):
            job_service = JobService()

            # Create a job
            job = job_service.create_job(
                tenant_id="integration-tenant",
                sql="SELECT id, name FROM products LIMIT 10",
                db_user="user_integration",
                output_format="json",
            )

            assert job.job_id.startswith("job-")
            assert job.tenant_id == "integration-tenant"
            assert job.status == JobStatus.QUEUED

            # Verify job can be retrieved
            retrieved = job_service.get_job(job.job_id)
            assert retrieved.job_id == job.job_id

    def test_job_status_updates(
        self, mock_aws_services: dict[str, Any], mock_redshift_client: MagicMock
    ) -> None:
        """Test that job status can be updated through the workflow."""
        from spectra.services.job import JobService
        from spectra.models.job import JobStatus, JobResult

        with patch("boto3.client", return_value=mock_redshift_client):
            job_service = JobService()

            # Create job
            job = job_service.create_job(
                tenant_id="integration-tenant",
                sql="SELECT * FROM test",
                db_user="user_integration",
            )

            # Update to SUBMITTED
            job = job_service.update_job_status(
                job_id=job.job_id,
                status=JobStatus.SUBMITTED,
                statement_id="stmt-123",
            )
            assert job.status == JobStatus.SUBMITTED

            # Update to RUNNING
            job = job_service.update_job_status(
                job_id=job.job_id,
                status=JobStatus.RUNNING,
            )
            assert job.status == JobStatus.RUNNING

            # Update to COMPLETED
            result = JobResult(row_count=100, location="inline")
            job = job_service.update_job_status(
                job_id=job.job_id,
                status=JobStatus.COMPLETED,
                result=result,
            )
            assert job.status == JobStatus.COMPLETED

    def test_tenant_isolation(
        self, mock_aws_services: dict[str, Any], mock_redshift_client: MagicMock
    ) -> None:
        """Test that jobs are isolated by tenant."""
        from spectra.services.job import JobService, JobNotFoundError

        with patch("boto3.client", return_value=mock_redshift_client):
            job_service = JobService()

            # Create job for tenant A
            job_a = job_service.create_job(
                tenant_id="tenant-A",
                sql="SELECT * FROM test",
                db_user="user_A",
            )

            # Create job for tenant B
            job_b = job_service.create_job(
                tenant_id="tenant-B",
                sql="SELECT * FROM test",
                db_user="user_B",
            )

            # Tenant A can access their job
            assert job_service.get_job(job_a.job_id, tenant_id="tenant-A")

            # Tenant A cannot access tenant B's job
            with pytest.raises(JobNotFoundError):
                job_service.get_job(job_b.job_id, tenant_id="tenant-A")


# =============================================================================
# Session Management Integration Tests
# =============================================================================


class TestSessionManagementIntegration:
    """Integration tests for session management."""

    def test_session_creation_and_retrieval(self, mock_aws_services: dict[str, Any]) -> None:
        """Test creating and retrieving sessions."""
        from spectra.services.session import SessionService

        session_service = SessionService()

        # Create a session
        session = session_service.create_session(
            session_id="session-int-123",
            tenant_id="tenant-session",
            db_user="user_session",
        )

        assert session.session_id == "session-int-123"
        assert session.is_active is True

        # Retrieve active session
        active = session_service.get_active_session(
            tenant_id="tenant-session",
            db_user="user_session",
        )

        assert active is not None
        assert active.session_id == "session-int-123"

    def test_session_reuse(self, mock_aws_services: dict[str, Any]) -> None:
        """Test session reuse logic."""
        from spectra.services.session import SessionService

        session_service = SessionService()

        # First call - no existing session
        session_id, is_new = session_service.get_or_create_session_id(
            tenant_id="tenant-reuse",
            db_user="user_reuse",
        )

        assert session_id is None
        assert is_new is True

        # Create a session
        session_service.create_session(
            session_id="session-reuse-123",
            tenant_id="tenant-reuse",
            db_user="user_reuse",
        )

        # Second call - should find existing session
        session_id, is_new = session_service.get_or_create_session_id(
            tenant_id="tenant-reuse",
            db_user="user_reuse",
        )

        assert session_id == "session-reuse-123"
        assert is_new is False

    def test_session_invalidation(self, mock_aws_services: dict[str, Any]) -> None:
        """Test session invalidation."""
        from spectra.services.session import SessionService

        session_service = SessionService()

        # Create a session
        session_service.create_session(
            session_id="session-to-invalidate",
            tenant_id="tenant-inv",
            db_user="user_inv",
        )

        # Invalidate the session
        session_service.invalidate_session("session-to-invalidate")

        # Session should no longer be active
        active = session_service.get_active_session(
            tenant_id="tenant-inv",
            db_user="user_inv",
        )

        assert active is None


# =============================================================================
# Export Integration Tests
# =============================================================================


class TestExportIntegration:
    """Integration tests for export functionality."""

    def test_export_json_to_s3(self, mock_aws_services: dict[str, Any]) -> None:
        """Test exporting JSON results to S3."""
        from spectra.services.export import ExportService

        export_service = ExportService()

        data = [
            {"id": 1, "name": "Product A", "price": 29.99},
            {"id": 2, "name": "Product B", "price": 49.99},
        ]

        s3_uri = export_service.write_json_results(
            job_id="job-export-123",
            tenant_id="tenant-export",
            data=data,
            metadata={"query_time_ms": 150},
        )

        assert s3_uri.startswith("s3://")

        # Verify the object was created
        s3 = mock_aws_services["s3"]
        bucket = s3_uri.split("/")[2]
        key = "/".join(s3_uri.split("/")[3:])

        response = s3.get_object(Bucket=bucket, Key=key)
        content = json.loads(response["Body"].read().decode("utf-8"))

        assert content["row_count"] == 2
        assert len(content["data"]) == 2

    def test_export_csv_to_s3(self, mock_aws_services: dict[str, Any]) -> None:
        """Test exporting CSV results to S3."""
        from spectra.services.export import ExportService

        export_service = ExportService()

        columns = ["id", "name", "price"]
        data = [
            {"id": 1, "name": "Product A", "price": 29.99},
            {"id": 2, "name": "Product B", "price": 49.99},
        ]

        s3_uri = export_service.write_csv_results(
            job_id="job-csv-123",
            tenant_id="tenant-csv",
            columns=columns,
            data=data,
        )

        assert s3_uri.endswith(".csv")

        # Verify the object was created
        s3 = mock_aws_services["s3"]
        bucket = s3_uri.split("/")[2]
        key = "/".join(s3_uri.split("/")[3:])

        response = s3.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8")

        # Normalize line endings for cross-platform compatibility
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        lines = content.strip().split("\n")
        assert lines[0] == "id,name,price"
        assert len(lines) == 3

    def test_presigned_url_generation(self, mock_aws_services: dict[str, Any]) -> None:
        """Test generating presigned URLs."""
        from spectra.services.export import ExportService

        export_service = ExportService()

        # First export something
        s3_uri = export_service.write_json_results(
            job_id="job-presigned-123",
            tenant_id="tenant-presigned",
            data=[{"id": 1}],
        )

        # Generate presigned URL
        url, expires_at = export_service.generate_presigned_url(
            s3_uri=s3_uri,
            expiry_seconds=3600,
        )

        assert url.startswith("https://")
        assert expires_at > datetime.now(UTC)


# =============================================================================
# End-to-End Workflow Tests
# =============================================================================


class TestEndToEndWorkflow:
    """End-to-end workflow integration tests."""

    @pytest.fixture
    def mock_redshift_client(self) -> MagicMock:
        """Create a mock Redshift Data API client."""
        mock = MagicMock()
        mock.execute_statement.return_value = {
            "Id": "stmt-e2e-123",
            "SessionId": "session-e2e-456",
        }
        return mock

    def test_complete_async_query_workflow(
        self, mock_aws_services: dict[str, Any], mock_redshift_client: MagicMock
    ) -> None:
        """Test complete async query workflow."""
        from spectra.services.job import JobService
        from spectra.services.export import ExportService
        from spectra.models.job import JobStatus, JobResult

        with patch("boto3.client", return_value=mock_redshift_client):
            job_service = JobService()
            export_service = ExportService()

            # Step 1: Submit query
            job = job_service.create_job(
                tenant_id="e2e-tenant",
                sql="SELECT * FROM orders WHERE status = 'active' LIMIT 100",
                db_user="user_e2e",
                output_format="json",
                async_mode=True,
            )

            assert job.status == JobStatus.QUEUED

            # Step 2: Update to submitted
            job = job_service.update_job_status(
                job_id=job.job_id,
                status=JobStatus.SUBMITTED,
                statement_id="stmt-e2e-123",
            )

            # Step 3: Update to running
            job = job_service.update_job_status(
                job_id=job.job_id,
                status=JobStatus.RUNNING,
            )

            # Step 4: Export results to S3
            result_data = [
                {"id": 1, "order_num": "ORD-001", "amount": 150.00},
                {"id": 2, "order_num": "ORD-002", "amount": 250.00},
            ]

            s3_uri = export_service.write_json_results(
                job_id=job.job_id,
                tenant_id=job.tenant_id,
                data=result_data,
            )

            # Step 5: Update to completed
            result = JobResult(
                row_count=len(result_data),
                location=s3_uri,
            )

            job = job_service.update_job_status(
                job_id=job.job_id,
                status=JobStatus.COMPLETED,
                result=result,
            )

            assert job.status == JobStatus.COMPLETED
            assert job.result is not None
            assert job.result.location == s3_uri

    def test_failed_query_workflow(
        self, mock_aws_services: dict[str, Any], mock_redshift_client: MagicMock
    ) -> None:
        """Test handling of failed queries."""
        from spectra.services.job import JobService
        from spectra.models.job import JobStatus, JobError

        with patch("boto3.client", return_value=mock_redshift_client):
            job_service = JobService()

            # Submit query
            job = job_service.create_job(
                tenant_id="e2e-failed",
                sql="SELECT * FROM nonexistent_table",
                db_user="user_failed",
            )

            # Update to submitted
            job = job_service.update_job_status(
                job_id=job.job_id,
                status=JobStatus.SUBMITTED,
                statement_id="stmt-failed-123",
            )

            # Update to failed
            error = JobError(
                code="RELATION_NOT_FOUND",
                message="Relation 'nonexistent_table' does not exist",
                details={"table": "nonexistent_table"},
            )

            job = job_service.update_job_status(
                job_id=job.job_id,
                status=JobStatus.FAILED,
                error=error,
            )

            assert job.status == JobStatus.FAILED
            assert job.error is not None
            assert job.error.code == "RELATION_NOT_FOUND"
