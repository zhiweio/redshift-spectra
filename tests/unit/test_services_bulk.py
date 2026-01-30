"""Unit tests for bulk job service.

Tests for the BulkJobService class that manages bulk import/export operations.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from spectra.models.bulk import (
    BulkJobInfo,
    BulkJobState,
    BulkOperation,
    CompressionType,
    DataFormat,
    LineEnding,
)
from spectra.services.bulk import (
    BulkJobNotFoundError,
    BulkJobService,
    BulkJobStateError,
)


# =============================================================================
# BulkJobService Tests
# =============================================================================


class TestBulkJobService:
    """Tests for BulkJobService class."""

    @pytest.fixture
    def mock_dynamodb_table(self) -> MagicMock:
        """Create a mock DynamoDB table."""
        return MagicMock()

    @pytest.fixture
    def mock_s3_client(self) -> MagicMock:
        """Create a mock S3 client."""
        return MagicMock()

    @pytest.fixture
    def bulk_service(
        self, mock_dynamodb_table: MagicMock, mock_s3_client: MagicMock
    ) -> BulkJobService:
        """Create a BulkJobService with mocked dependencies."""
        with patch("boto3.resource") as mock_resource, patch("boto3.client") as mock_client:
            mock_resource.return_value.Table.return_value = mock_dynamodb_table
            mock_client.return_value = mock_s3_client
            service = BulkJobService()
            service.table = mock_dynamodb_table
            service.s3_client = mock_s3_client
            return service

    def test_generate_job_id(self) -> None:
        """Test bulk job ID generation format."""
        job_id = BulkJobService.generate_job_id()

        assert job_id.startswith("bulk-")
        assert len(job_id) == 21  # "bulk-" + 16 hex chars

    def test_generate_job_id_uniqueness(self) -> None:
        """Test that bulk job IDs are unique."""
        ids = {BulkJobService.generate_job_id() for _ in range(100)}
        assert len(ids) == 100

    def test_get_file_extension_csv(self) -> None:
        """Test file extension for CSV format."""
        ext = BulkJobService._get_file_extension(DataFormat.CSV, CompressionType.NONE)
        assert ext == ".csv"

    def test_get_file_extension_csv_gzip(self) -> None:
        """Test file extension for gzipped CSV."""
        ext = BulkJobService._get_file_extension(DataFormat.CSV, CompressionType.GZIP)
        assert ext == ".csv.gz"

    def test_get_file_extension_json(self) -> None:
        """Test file extension for JSON format."""
        ext = BulkJobService._get_file_extension(DataFormat.JSON, CompressionType.NONE)
        assert ext == ".json"

    def test_get_file_extension_parquet(self) -> None:
        """Test file extension for Parquet (no compression suffix)."""
        ext = BulkJobService._get_file_extension(DataFormat.PARQUET, CompressionType.GZIP)
        assert ext == ".parquet"

    def test_get_file_extension_csv_zstd(self) -> None:
        """Test file extension for zstd compressed CSV."""
        ext = BulkJobService._get_file_extension(DataFormat.CSV, CompressionType.ZSTD)
        assert ext == ".csv.zst"

    def test_create_query_job(
        self, bulk_service: BulkJobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test creating a query (export) job."""
        mock_dynamodb_table.put_item.return_value = {}

        job_info = bulk_service.create_job(
            tenant_id="tenant-123",
            db_user="user_tenant_123",
            operation=BulkOperation.QUERY,
            query="SELECT * FROM large_table",
            content_type=DataFormat.CSV,
            compression=CompressionType.GZIP,
        )

        assert job_info.id.startswith("bulk-")
        assert job_info.created_by_id == "tenant-123"
        assert job_info.operation == BulkOperation.QUERY
        assert job_info.content_type == DataFormat.CSV
        mock_dynamodb_table.put_item.assert_called_once()

    def test_create_insert_job(
        self, bulk_service: BulkJobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test creating an insert job."""
        mock_dynamodb_table.put_item.return_value = {}

        job_info = bulk_service.create_job(
            tenant_id="tenant-123",
            db_user="user_tenant_123",
            operation=BulkOperation.INSERT,
            object_name="target_table",
            content_type=DataFormat.CSV,
        )

        assert job_info.operation == BulkOperation.INSERT
        assert job_info.object == "target_table"

    def test_create_upsert_job(
        self, bulk_service: BulkJobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test creating an upsert job with external ID field."""
        mock_dynamodb_table.put_item.return_value = {}

        job_info = bulk_service.create_job(
            tenant_id="tenant-123",
            db_user="user_tenant_123",
            operation=BulkOperation.UPSERT,
            object_name="target_table",
            external_id_field="record_id",
        )

        assert job_info.operation == BulkOperation.UPSERT
        assert job_info.object == "target_table"

    def test_create_job_missing_query_for_export(self, bulk_service: BulkJobService) -> None:
        """Test that query is required for export operations."""
        with pytest.raises(ValueError, match="Query is required"):
            bulk_service.create_job(
                tenant_id="tenant-123",
                db_user="user_tenant_123",
                operation=BulkOperation.QUERY,
            )

    def test_create_job_missing_object_for_import(self, bulk_service: BulkJobService) -> None:
        """Test that object name is required for import operations."""
        with pytest.raises(ValueError, match="Object.*is required"):
            bulk_service.create_job(
                tenant_id="tenant-123",
                db_user="user_tenant_123",
                operation=BulkOperation.INSERT,
            )

    def test_get_job_found(
        self, bulk_service: BulkJobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test getting an existing bulk job."""
        job_data = self._make_bulk_job_item("bulk-123", "tenant-123")
        mock_dynamodb_table.get_item.return_value = {"Item": job_data}

        job_info = bulk_service.get_job("bulk-123", "tenant-123")

        assert job_info.id == "bulk-123"
        assert job_info.created_by_id == "tenant-123"

    def test_get_job_not_found(
        self, bulk_service: BulkJobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test getting a non-existent bulk job."""
        mock_dynamodb_table.get_item.return_value = {}

        with pytest.raises(BulkJobNotFoundError):
            bulk_service.get_job("non-existent", "tenant-123")

    def test_get_job_tenant_validation(
        self, bulk_service: BulkJobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test that tenant ID is validated."""
        job_data = self._make_bulk_job_item("bulk-123", "tenant-123")
        mock_dynamodb_table.get_item.return_value = {"Item": job_data}

        with pytest.raises(BulkJobNotFoundError):
            bulk_service.get_job("bulk-123", "different-tenant")

    def test_list_jobs(self, bulk_service: BulkJobService, mock_dynamodb_table: MagicMock) -> None:
        """Test listing bulk jobs for a tenant."""
        job1 = self._make_bulk_job_item("bulk-1", "tenant-123")
        job2 = self._make_bulk_job_item("bulk-2", "tenant-123")
        mock_dynamodb_table.query.return_value = {"Items": [job1, job2]}

        jobs, next_key = bulk_service.list_jobs("tenant-123")

        assert len(jobs) == 2
        assert jobs[0].id == "bulk-1"

    def _make_bulk_job_item(self, job_id: str, tenant_id: str) -> dict[str, Any]:
        """Create a sample bulk job item for testing."""
        now = datetime.now(UTC)
        return {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "db_user": f"user_{tenant_id}",
            "operation": "query",
            "state": "Open",
            "content_type": "CSV",
            "compression": "GZIP",
            "line_ending": "LF",
            "column_delimiter": ",",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "ttl": int(now.timestamp() + 86400 * 7),
        }


class TestBulkJobStateTransitions:
    """Tests for bulk job state transitions."""

    @pytest.fixture
    def mock_dynamodb_table(self) -> MagicMock:
        """Create a mock DynamoDB table."""
        return MagicMock()

    @pytest.fixture
    def mock_s3_client(self) -> MagicMock:
        """Create a mock S3 client."""
        return MagicMock()

    @pytest.fixture
    def bulk_service(
        self, mock_dynamodb_table: MagicMock, mock_s3_client: MagicMock
    ) -> BulkJobService:
        """Create a BulkJobService with mocked dependencies."""
        with patch("boto3.resource") as mock_resource, patch("boto3.client") as mock_client:
            mock_resource.return_value.Table.return_value = mock_dynamodb_table
            mock_client.return_value = mock_s3_client
            service = BulkJobService()
            service.table = mock_dynamodb_table
            service.s3_client = mock_s3_client
            return service

    def test_update_job_state_open_to_upload_complete(
        self, bulk_service: BulkJobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test transitioning from Open to UploadComplete."""
        now = datetime.now(UTC)
        current_job = {
            "job_id": "bulk-123",
            "tenant_id": "tenant-123",
            "db_user": "user_tenant_123",
            "operation": "insert",
            "state": "Open",
            "content_type": "CSV",
            "compression": "GZIP",
            "line_ending": "LF",
            "column_delimiter": ",",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        # Mock get_item for get_job call
        mock_dynamodb_table.get_item.return_value = {"Item": current_job}
        # Mock update_item for state transition
        updated_job = {**current_job, "state": "UploadComplete"}
        mock_dynamodb_table.update_item.return_value = {"Attributes": updated_job}

        job_info = bulk_service.update_job_state(
            job_id="bulk-123",
            tenant_id="tenant-123",
            new_state=BulkJobState.UPLOAD_COMPLETE,
        )

        assert job_info.state == BulkJobState.UPLOAD_COMPLETE
        mock_dynamodb_table.update_item.assert_called_once()


class TestBulkJobExceptions:
    """Tests for bulk job exception classes."""

    def test_bulk_job_not_found_error(self) -> None:
        """Test BulkJobNotFoundError."""
        error = BulkJobNotFoundError("Job not found")

        assert str(error) == "Job not found"

    def test_bulk_job_state_error(self) -> None:
        """Test BulkJobStateError."""
        error = BulkJobStateError(
            job_id="bulk-123",
            current_state="Open",
            requested_state="JobComplete",
        )

        assert "bulk-123" in str(error)
        assert "Open" in str(error)
        assert "JobComplete" in str(error)
        assert error.job_id == "bulk-123"
        assert error.current_state == "Open"
        assert error.requested_state == "JobComplete"
