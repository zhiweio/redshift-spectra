"""Integration tests for bulk job operations.

These tests verify the complete bulk import/export workflow
using mocked AWS services.
"""

import os
from collections.abc import Generator
from typing import Any

import boto3
import pytest
from moto import mock_aws

from spectra.models.bulk import (
    BulkJobState,
    BulkOperation,
    CompressionType,
    DataFormat,
)

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
    """Set up all mocked AWS services for bulk operations."""
    with mock_aws():
        # Create DynamoDB tables
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        # Bulk jobs table
        bulk_table = dynamodb.create_table(
            TableName="spectra-bulk-jobs",
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "tenant_id", "AttributeType": "S"},
                {"AttributeName": "state", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "gsi1-tenant",
                    "KeySchema": [{"AttributeName": "tenant_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "tenant-state-index",
                    "KeySchema": [
                        {"AttributeName": "tenant_id", "KeyType": "HASH"},
                        {"AttributeName": "state", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Sessions table (for session reuse)
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

        # Create S3 bucket
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")

        yield {
            "dynamodb": dynamodb,
            "bulk_table": bulk_table,
            "sessions_table": sessions_table,
            "jobs_table": jobs_table,
            "s3": s3,
        }


# =============================================================================
# Bulk Export (Query) Integration Tests
# =============================================================================


class TestBulkExportIntegration:
    """Integration tests for bulk export operations."""

    def test_create_query_job(self, mock_aws_services: dict[str, Any]) -> None:
        """Test creating a bulk query (export) job."""
        from spectra.services.bulk import BulkJobService

        bulk_service = BulkJobService()

        job = bulk_service.create_job(
            tenant_id="bulk-tenant",
            db_user="user_bulk",
            operation=BulkOperation.QUERY,
            query="SELECT * FROM large_table WHERE date >= '2024-01-01'",
            content_type=DataFormat.CSV,
            compression=CompressionType.GZIP,
        )

        assert job.id.startswith("bulk-")
        assert job.operation == BulkOperation.QUERY
        assert job.content_type == DataFormat.CSV

    def test_query_job_workflow(self, mock_aws_services: dict[str, Any]) -> None:
        """Test complete query job workflow."""
        from spectra.services.bulk import BulkJobService

        bulk_service = BulkJobService()

        # Create job
        job = bulk_service.create_job(
            tenant_id="bulk-workflow",
            db_user="user_workflow",
            operation=BulkOperation.QUERY,
            query="SELECT * FROM sales",
            content_type=DataFormat.JSON,
        )

        # For query jobs, state starts as InProgress, can go directly to JobComplete
        job = bulk_service.update_job_state(
            job_id=job.id,
            tenant_id=job.created_by_id,
            new_state=BulkJobState.JOB_COMPLETE,
        )

        assert job.state == BulkJobState.JOB_COMPLETE

    def test_export_to_parquet(self, mock_aws_services: dict[str, Any]) -> None:
        """Test exporting to Parquet format."""
        from spectra.services.bulk import BulkJobService

        bulk_service = BulkJobService()

        job = bulk_service.create_job(
            tenant_id="bulk-parquet",
            db_user="user_parquet",
            operation=BulkOperation.QUERY,
            query="SELECT * FROM analytics",
            content_type=DataFormat.PARQUET,
            compression=CompressionType.ZSTD,
        )

        assert job.content_type == DataFormat.PARQUET
        assert job.compression == CompressionType.ZSTD


# =============================================================================
# Bulk Import Integration Tests
# =============================================================================


class TestBulkImportIntegration:
    """Integration tests for bulk import operations."""

    def test_create_insert_job(self, mock_aws_services: dict[str, Any]) -> None:
        """Test creating a bulk insert job."""
        from spectra.services.bulk import BulkJobService

        bulk_service = BulkJobService()

        job = bulk_service.create_job(
            tenant_id="bulk-insert",
            db_user="user_insert",
            operation=BulkOperation.INSERT,
            object_name="target_table",
            content_type=DataFormat.CSV,
        )

        assert job.operation == BulkOperation.INSERT
        assert job.object == "target_table"
        assert job.state == BulkJobState.OPEN

    def test_create_upsert_job(self, mock_aws_services: dict[str, Any]) -> None:
        """Test creating a bulk upsert job."""
        from spectra.services.bulk import BulkJobService

        bulk_service = BulkJobService()

        job = bulk_service.create_job(
            tenant_id="bulk-upsert",
            db_user="user_upsert",
            operation=BulkOperation.UPSERT,
            object_name="target_table",
            external_id_field="record_id",
        )

        assert job.operation == BulkOperation.UPSERT
        assert job.object == "target_table"

    def test_import_job_workflow(self, mock_aws_services: dict[str, Any]) -> None:
        """Test complete import job workflow."""
        from spectra.services.bulk import BulkJobService

        bulk_service = BulkJobService()

        # Create job (Open state)
        job = bulk_service.create_job(
            tenant_id="bulk-import-wf",
            db_user="user_import",
            operation=BulkOperation.INSERT,
            object_name="import_table",
        )

        assert job.state == BulkJobState.OPEN

        # Close job (UploadComplete) - triggers processing
        job = bulk_service.update_job_state(
            job_id=job.id,
            tenant_id=job.created_by_id,
            new_state=BulkJobState.UPLOAD_COMPLETE,
        )

        assert job.state == BulkJobState.UPLOAD_COMPLETE

        # InProgress state
        job = bulk_service.update_job_state(
            job_id=job.id,
            tenant_id=job.created_by_id,
            new_state=BulkJobState.IN_PROGRESS,
        )

        assert job.state == BulkJobState.IN_PROGRESS

        # Complete
        job = bulk_service.update_job_state(
            job_id=job.id,
            tenant_id=job.created_by_id,
            new_state=BulkJobState.JOB_COMPLETE,
        )

        assert job.state == BulkJobState.JOB_COMPLETE


# =============================================================================
# Bulk Job Management Integration Tests
# =============================================================================


class TestBulkJobManagementIntegration:
    """Integration tests for bulk job management."""

    def test_list_jobs_by_tenant(self, mock_aws_services: dict[str, Any]) -> None:
        """Test listing jobs filtered by tenant."""
        from spectra.services.bulk import BulkJobService

        bulk_service = BulkJobService()

        # Create jobs for different tenants
        for i in range(3):
            bulk_service.create_job(
                tenant_id="list-tenant-A",
                db_user="user_A",
                operation=BulkOperation.QUERY,
                query=f"SELECT * FROM table_{i}",
            )

        for i in range(2):
            bulk_service.create_job(
                tenant_id="list-tenant-B",
                db_user="user_B",
                operation=BulkOperation.QUERY,
                query=f"SELECT * FROM table_{i}",
            )

        # List tenant A's jobs
        jobs_a, _ = bulk_service.list_jobs("list-tenant-A")
        assert len(jobs_a) == 3

        # List tenant B's jobs
        jobs_b, _ = bulk_service.list_jobs("list-tenant-B")
        assert len(jobs_b) == 2

    def test_get_job_with_tenant_validation(self, mock_aws_services: dict[str, Any]) -> None:
        """Test that job retrieval validates tenant access."""
        from spectra.services.bulk import BulkJobNotFoundError, BulkJobService

        bulk_service = BulkJobService()

        # Create job for tenant A
        job = bulk_service.create_job(
            tenant_id="owner-tenant",
            db_user="user_owner",
            operation=BulkOperation.QUERY,
            query="SELECT * FROM data",
        )

        # Owner can access
        retrieved = bulk_service.get_job(job.id, "owner-tenant")
        assert retrieved.id == job.id

        # Other tenant cannot access
        with pytest.raises(BulkJobNotFoundError):
            bulk_service.get_job(job.id, "other-tenant")

    def test_abort_job(self, mock_aws_services: dict[str, Any]) -> None:
        """Test aborting a bulk job."""
        from spectra.services.bulk import BulkJobService

        bulk_service = BulkJobService()

        # Create job
        job = bulk_service.create_job(
            tenant_id="abort-tenant",
            db_user="user_abort",
            operation=BulkOperation.INSERT,
            object_name="abort_table",
        )

        # Abort the job
        job = bulk_service.update_job_state(
            job_id=job.id,
            tenant_id=job.created_by_id,
            new_state=BulkJobState.ABORTED,
        )

        assert job.state == BulkJobState.ABORTED


# =============================================================================
# Bulk Job Error Handling Integration Tests
# =============================================================================


class TestBulkJobErrorHandling:
    """Integration tests for bulk job error handling."""

    def test_failed_job(self, mock_aws_services: dict[str, Any]) -> None:
        """Test marking a job as failed."""
        from spectra.services.bulk import BulkJobService

        bulk_service = BulkJobService()

        # Create and start job
        job = bulk_service.create_job(
            tenant_id="fail-tenant",
            db_user="user_fail",
            operation=BulkOperation.INSERT,
            object_name="fail_table",
        )

        # First transition to UploadComplete, then InProgress
        job = bulk_service.update_job_state(
            job_id=job.id,
            tenant_id=job.created_by_id,
            new_state=BulkJobState.UPLOAD_COMPLETE,
        )

        job = bulk_service.update_job_state(
            job_id=job.id,
            tenant_id=job.created_by_id,
            new_state=BulkJobState.IN_PROGRESS,
        )

        # Mark as failed
        job = bulk_service.update_job_state(
            job_id=job.id,
            tenant_id=job.created_by_id,
            new_state=BulkJobState.FAILED,
        )

        assert job.state == BulkJobState.FAILED

    def test_missing_required_fields(self, mock_aws_services: dict[str, Any]) -> None:
        """Test validation of required fields."""
        from spectra.services.bulk import BulkJobService

        bulk_service = BulkJobService()

        # Query without SQL
        with pytest.raises(ValueError, match="Query is required"):
            bulk_service.create_job(
                tenant_id="val-tenant",
                db_user="user_val",
                operation=BulkOperation.QUERY,
            )

        # Insert without object name
        with pytest.raises(ValueError, match=r"Object.*is required"):
            bulk_service.create_job(
                tenant_id="val-tenant",
                db_user="user_val",
                operation=BulkOperation.INSERT,
            )


# =============================================================================
# Data Format Integration Tests
# =============================================================================


class TestDataFormatIntegration:
    """Integration tests for different data formats."""

    def test_csv_with_custom_delimiter(self, mock_aws_services: dict[str, Any]) -> None:
        """Test CSV with custom column delimiter."""
        from spectra.services.bulk import BulkJobService

        bulk_service = BulkJobService()

        job = bulk_service.create_job(
            tenant_id="csv-tenant",
            db_user="user_csv",
            operation=BulkOperation.QUERY,
            query="SELECT * FROM data",
            content_type=DataFormat.CSV,
            column_delimiter="|",
        )

        assert job.column_delimiter == "|"

    def test_json_format(self, mock_aws_services: dict[str, Any]) -> None:
        """Test JSON format export."""
        from spectra.services.bulk import BulkJobService

        bulk_service = BulkJobService()

        job = bulk_service.create_job(
            tenant_id="json-tenant",
            db_user="user_json",
            operation=BulkOperation.QUERY,
            query="SELECT * FROM data",
            content_type=DataFormat.JSON,
            compression=CompressionType.GZIP,
        )

        assert job.content_type == DataFormat.JSON
        assert job.compression == CompressionType.GZIP

    def test_various_compression_types(self, mock_aws_services: dict[str, Any]) -> None:
        """Test different compression options."""
        from spectra.services.bulk import BulkJobService

        bulk_service = BulkJobService()

        compression_types = [
            CompressionType.NONE,
            CompressionType.GZIP,
            CompressionType.BZIP2,
            CompressionType.ZSTD,
        ]

        for compression in compression_types:
            job = bulk_service.create_job(
                tenant_id=f"comp-{compression.value}",
                db_user="user_comp",
                operation=BulkOperation.QUERY,
                query="SELECT 1",
                compression=compression,
            )

            assert job.compression == compression
