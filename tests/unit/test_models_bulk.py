"""Unit tests for bulk API models.

Tests cover:
- Bulk operation and state enums
- Request model validation (create, update)
- Response model serialization
- BulkJob DynamoDB serialization
- Edge cases and error handling
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from spectra.models.bulk import (
    BulkJob,
    BulkJobCreateRequest,
    BulkJobInfo,
    BulkJobListResponse,
    BulkJobResponse,
    BulkJobResult,
    BulkJobState,
    BulkJobUpdateRequest,
    BulkOperation,
    ColumnMapping,
    CompressionType,
    DataFormat,
    LineEnding,
)

# =============================================================================
# Enum Tests
# =============================================================================


class TestBulkOperation:
    """Tests for BulkOperation enum."""

    def test_operation_values(self) -> None:
        """Test all operation values exist."""
        operations = [
            BulkOperation.QUERY,
            BulkOperation.INSERT,
            BulkOperation.UPDATE,
            BulkOperation.UPSERT,
            BulkOperation.DELETE,
        ]
        assert len(operations) == 5

    def test_operation_string_values(self) -> None:
        """Test operation string values."""
        assert BulkOperation.QUERY.value == "query"
        assert BulkOperation.INSERT.value == "insert"
        assert BulkOperation.UPDATE.value == "update"
        assert BulkOperation.UPSERT.value == "upsert"
        assert BulkOperation.DELETE.value == "delete"


class TestBulkJobState:
    """Tests for BulkJobState enum."""

    def test_state_values(self) -> None:
        """Test all state values exist."""
        states = [
            BulkJobState.OPEN,
            BulkJobState.UPLOAD_COMPLETE,
            BulkJobState.IN_PROGRESS,
            BulkJobState.JOB_COMPLETE,
            BulkJobState.FAILED,
            BulkJobState.ABORTED,
        ]
        assert len(states) == 6

    def test_terminal_states(self) -> None:
        """Test terminal state detection."""
        assert BulkJobState.JOB_COMPLETE.is_terminal is True
        assert BulkJobState.FAILED.is_terminal is True
        assert BulkJobState.ABORTED.is_terminal is True

        assert BulkJobState.OPEN.is_terminal is False
        assert BulkJobState.UPLOAD_COMPLETE.is_terminal is False
        assert BulkJobState.IN_PROGRESS.is_terminal is False

    def test_state_string_values(self) -> None:
        """Test state string values (Salesforce compatible)."""
        assert BulkJobState.OPEN.value == "Open"
        assert BulkJobState.UPLOAD_COMPLETE.value == "UploadComplete"
        assert BulkJobState.IN_PROGRESS.value == "InProgress"
        assert BulkJobState.JOB_COMPLETE.value == "JobComplete"
        assert BulkJobState.FAILED.value == "Failed"
        assert BulkJobState.ABORTED.value == "Aborted"


class TestDataFormat:
    """Tests for DataFormat enum."""

    def test_format_values(self) -> None:
        """Test all format values."""
        assert DataFormat.CSV.value == "CSV"
        assert DataFormat.JSON.value == "JSON"
        assert DataFormat.PARQUET.value == "PARQUET"


class TestCompressionType:
    """Tests for CompressionType enum."""

    def test_compression_values(self) -> None:
        """Test all compression values."""
        compressions = [
            CompressionType.NONE,
            CompressionType.GZIP,
            CompressionType.LZOP,
            CompressionType.BZIP2,
            CompressionType.ZSTD,
        ]
        assert len(compressions) == 5


class TestLineEnding:
    """Tests for LineEnding enum."""

    def test_line_ending_values(self) -> None:
        """Test line ending values."""
        assert LineEnding.LF.value == "LF"
        assert LineEnding.CRLF.value == "CRLF"


# =============================================================================
# Request Model Tests
# =============================================================================


class TestColumnMapping:
    """Tests for ColumnMapping model."""

    def test_valid_mapping(self) -> None:
        """Test creating valid column mapping."""
        mapping = ColumnMapping(
            source_column="src_col",
            target_column="tgt_col",
        )
        assert mapping.source_column == "src_col"
        assert mapping.target_column == "tgt_col"
        assert mapping.transform is None

    def test_mapping_with_transform(self) -> None:
        """Test mapping with SQL transformation."""
        mapping = ColumnMapping(
            source_column="date_str",
            target_column="date_col",
            transform="TO_DATE(date_str, 'YYYY-MM-DD')",
        )
        assert mapping.transform is not None


class TestBulkJobCreateRequest:
    """Tests for BulkJobCreateRequest model."""

    def test_valid_query_request(self) -> None:
        """Test creating valid query (export) request."""
        request = BulkJobCreateRequest(
            operation=BulkOperation.QUERY,
            query="SELECT * FROM users WHERE status = 'active'",
            content_type=DataFormat.CSV,
        )
        assert request.operation == BulkOperation.QUERY
        assert "SELECT" in request.query
        assert request.content_type == DataFormat.CSV

    def test_valid_insert_request(self) -> None:
        """Test creating valid insert (import) request."""
        request = BulkJobCreateRequest(
            operation=BulkOperation.INSERT,
            object="users",
            content_type=DataFormat.CSV,
        )
        assert request.operation == BulkOperation.INSERT
        assert request.object == "users"

    def test_valid_upsert_request(self) -> None:
        """Test creating valid upsert request with external ID."""
        request = BulkJobCreateRequest(
            operation=BulkOperation.UPSERT,
            object="contacts",
            external_id_field="email",
            content_type=DataFormat.JSON,
        )
        assert request.operation == BulkOperation.UPSERT
        assert request.external_id_field == "email"

    def test_query_validation_select_only(self) -> None:
        """Test that query must start with SELECT."""
        with pytest.raises(ValidationError) as exc_info:
            BulkJobCreateRequest(
                operation=BulkOperation.QUERY,
                query="INSERT INTO users VALUES (1)",
            )
        assert "SELECT" in str(exc_info.value)

    def test_query_validation_empty_rejected(self) -> None:
        """Test that empty query is rejected."""
        with pytest.raises(ValidationError):
            BulkJobCreateRequest(
                operation=BulkOperation.QUERY,
                query="   ",
            )

    def test_object_validation_sql_injection(self) -> None:
        """Test SQL injection prevention in object name."""
        with pytest.raises(ValidationError):
            BulkJobCreateRequest(
                operation=BulkOperation.INSERT,
                object="users; DROP TABLE users--",
            )

    def test_object_validation_empty_rejected(self) -> None:
        """Test that empty object name is rejected."""
        with pytest.raises(ValidationError):
            BulkJobCreateRequest(
                operation=BulkOperation.INSERT,
                object="   ",
            )

    def test_default_values(self) -> None:
        """Test default values."""
        request = BulkJobCreateRequest(
            operation=BulkOperation.QUERY,
            query="SELECT 1",
        )
        assert request.content_type == DataFormat.CSV
        assert request.compression == CompressionType.GZIP
        assert request.line_ending == LineEnding.LF
        assert request.column_delimiter == ","

    def test_with_column_mappings(self) -> None:
        """Test request with column mappings."""
        request = BulkJobCreateRequest(
            operation=BulkOperation.INSERT,
            object="users",
            column_mappings=[
                ColumnMapping(source_column="name", target_column="full_name"),
                ColumnMapping(source_column="email", target_column="email_address"),
            ],
        )
        assert len(request.column_mappings) == 2

    def test_parquet_format(self) -> None:
        """Test request with Parquet format."""
        request = BulkJobCreateRequest(
            operation=BulkOperation.QUERY,
            query="SELECT * FROM large_table",
            content_type=DataFormat.PARQUET,
            compression=CompressionType.ZSTD,
        )
        assert request.content_type == DataFormat.PARQUET
        assert request.compression == CompressionType.ZSTD


class TestBulkJobUpdateRequest:
    """Tests for BulkJobUpdateRequest model."""

    def test_upload_complete_state(self) -> None:
        """Test setting UploadComplete state."""
        request = BulkJobUpdateRequest(state="UploadComplete")
        assert request.state == "UploadComplete"

    def test_aborted_state(self) -> None:
        """Test setting Aborted state."""
        request = BulkJobUpdateRequest(state="Aborted")
        assert request.state == "Aborted"

    def test_invalid_state_rejected(self) -> None:
        """Test that invalid state is rejected."""
        with pytest.raises(ValidationError):
            BulkJobUpdateRequest(state="InProgress")


# =============================================================================
# Response Model Tests
# =============================================================================


class TestBulkJobInfo:
    """Tests for BulkJobInfo response model."""

    def test_valid_info(self) -> None:
        """Test creating valid job info."""
        now = datetime.now(UTC)
        info = BulkJobInfo(
            id="bulk-123",
            operation=BulkOperation.QUERY,
            state=BulkJobState.IN_PROGRESS,
            content_type=DataFormat.CSV,
            compression=CompressionType.GZIP,
            created_at=now,
            created_by_id="tenant-456",
            system_modstamp=now,
        )
        assert info.id == "bulk-123"
        assert info.operation == BulkOperation.QUERY
        assert info.state == BulkJobState.IN_PROGRESS

    def test_info_with_urls(self) -> None:
        """Test info with content URL."""
        now = datetime.now(UTC)
        info = BulkJobInfo(
            id="bulk-123",
            operation=BulkOperation.INSERT,
            state=BulkJobState.OPEN,
            content_type=DataFormat.CSV,
            compression=CompressionType.GZIP,
            content_url="s3://bucket/upload/path",
            content_url_expires_at=now,
            created_at=now,
            created_by_id="tenant-456",
            system_modstamp=now,
        )
        assert info.content_url is not None
        assert info.content_url_expires_at is not None

    def test_info_with_error(self) -> None:
        """Test info for failed job."""
        now = datetime.now(UTC)
        info = BulkJobInfo(
            id="bulk-123",
            operation=BulkOperation.QUERY,
            state=BulkJobState.FAILED,
            content_type=DataFormat.CSV,
            compression=CompressionType.GZIP,
            created_at=now,
            created_by_id="tenant-456",
            system_modstamp=now,
            error_message="Connection timeout",
        )
        assert info.state == BulkJobState.FAILED
        assert info.error_message == "Connection timeout"


class TestBulkJobResult:
    """Tests for BulkJobResult model."""

    def test_default_values(self) -> None:
        """Test default values."""
        result = BulkJobResult()
        assert result.number_records_processed == 0
        assert result.number_records_failed == 0
        assert result.total_processing_time_ms == 0
        assert result.result_files == []

    def test_with_statistics(self) -> None:
        """Test result with processing statistics."""
        result = BulkJobResult(
            number_records_processed=10000,
            number_records_failed=5,
            total_processing_time_ms=5000,
            result_file_count=3,
            total_size_bytes=1024 * 1024 * 50,
        )
        assert result.number_records_processed == 10000
        assert result.number_records_failed == 5
        assert result.total_size_bytes == 1024 * 1024 * 50

    def test_with_download_urls(self) -> None:
        """Test result with download URLs."""
        now = datetime.now(UTC)
        result = BulkJobResult(
            number_records_processed=100,
            successful_results_url="https://s3.amazonaws.com/bucket/success.csv",
            failed_results_url="https://s3.amazonaws.com/bucket/failed.csv",
            urls_expire_at=now,
        )
        assert result.successful_results_url is not None
        assert result.failed_results_url is not None
        assert result.urls_expire_at == now


class TestBulkJobResponse:
    """Tests for BulkJobResponse model."""

    def test_info_only(self) -> None:
        """Test response with info only."""
        now = datetime.now(UTC)
        info = BulkJobInfo(
            id="bulk-123",
            operation=BulkOperation.QUERY,
            state=BulkJobState.IN_PROGRESS,
            content_type=DataFormat.CSV,
            compression=CompressionType.GZIP,
            created_at=now,
            created_by_id="tenant-456",
            system_modstamp=now,
        )
        response = BulkJobResponse(info=info)
        assert response.info.id == "bulk-123"
        assert response.results is None

    def test_with_results(self) -> None:
        """Test response with both info and results."""
        now = datetime.now(UTC)
        info = BulkJobInfo(
            id="bulk-123",
            operation=BulkOperation.QUERY,
            state=BulkJobState.JOB_COMPLETE,
            content_type=DataFormat.CSV,
            compression=CompressionType.GZIP,
            created_at=now,
            created_by_id="tenant-456",
            system_modstamp=now,
        )
        results = BulkJobResult(
            number_records_processed=1000,
        )
        response = BulkJobResponse(info=info, results=results)
        assert response.results is not None
        assert response.results.number_records_processed == 1000


class TestBulkJobListResponse:
    """Tests for BulkJobListResponse model."""

    def test_empty_list(self) -> None:
        """Test empty job list."""
        response = BulkJobListResponse(
            done=True,
            records=[],
            total_size=0,
        )
        assert response.done is True
        assert len(response.records) == 0
        assert response.next_records_url is None

    def test_paginated_list(self) -> None:
        """Test paginated job list."""
        now = datetime.now(UTC)
        jobs = [
            BulkJobInfo(
                id=f"bulk-{i}",
                operation=BulkOperation.QUERY,
                state=BulkJobState.JOB_COMPLETE,
                content_type=DataFormat.CSV,
                compression=CompressionType.GZIP,
                created_at=now,
                created_by_id="tenant-456",
                system_modstamp=now,
            )
            for i in range(10)
        ]
        response = BulkJobListResponse(
            done=False,
            records=jobs,
            next_records_url="/v1/bulk/jobs?cursor=abc123",
            total_size=25,
        )
        assert response.done is False
        assert len(response.records) == 10
        assert response.next_records_url is not None
        assert response.total_size == 25


# =============================================================================
# BulkJob DynamoDB Model Tests
# =============================================================================


class TestBulkJob:
    """Tests for BulkJob DynamoDB model."""

    @pytest.fixture
    def sample_bulk_job(self) -> BulkJob:
        """Create sample bulk job for testing."""
        now = datetime.now(UTC)
        return BulkJob(
            job_id="bulk-abc123",
            tenant_id="tenant-123",
            operation=BulkOperation.QUERY,
            state=BulkJobState.IN_PROGRESS,
            query="SELECT * FROM users",
            content_type=DataFormat.CSV,
            compression=CompressionType.GZIP,
            db_user="user_tenant_123",
            created_at=now,
            updated_at=now,
        )

    def test_job_creation(self, sample_bulk_job: BulkJob) -> None:
        """Test bulk job creation."""
        assert sample_bulk_job.job_id == "bulk-abc123"
        assert sample_bulk_job.tenant_id == "tenant-123"
        assert sample_bulk_job.operation == BulkOperation.QUERY
        assert sample_bulk_job.state == BulkJobState.IN_PROGRESS

    def test_default_values(self) -> None:
        """Test default values."""
        now = datetime.now(UTC)
        job = BulkJob(
            job_id="bulk-123",
            tenant_id="tenant-123",
            operation=BulkOperation.INSERT,
            db_user="user",
            created_at=now,
            updated_at=now,
        )
        assert job.state == BulkJobState.OPEN
        assert job.content_type == DataFormat.CSV
        assert job.compression == CompressionType.GZIP
        assert job.records_processed == 0
        assert job.records_failed == 0

    def test_import_job_creation(self) -> None:
        """Test import job with object."""
        now = datetime.now(UTC)
        job = BulkJob(
            job_id="bulk-123",
            tenant_id="tenant-123",
            operation=BulkOperation.INSERT,
            object="users",
            content_type=DataFormat.CSV,
            db_user="user",
            created_at=now,
            updated_at=now,
            s3_input_prefix="s3://bucket/input/bulk-123/",
        )
        assert job.object == "users"
        assert job.s3_input_prefix is not None

    def test_to_info(self, sample_bulk_job: BulkJob) -> None:
        """Test conversion to BulkJobInfo."""
        info = sample_bulk_job.to_info(
            content_url="s3://bucket/results",
            url_expires=datetime.now(UTC),
        )
        assert info.id == "bulk-abc123"
        assert info.operation == BulkOperation.QUERY
        assert info.state == BulkJobState.IN_PROGRESS
        assert info.content_url == "s3://bucket/results"

    def test_to_info_masks_long_query(self) -> None:
        """Test that long queries are masked in info."""
        now = datetime.now(UTC)
        long_query = "SELECT " + ", ".join([f"col{i}" for i in range(50)]) + " FROM big_table"
        job = BulkJob(
            job_id="bulk-123",
            tenant_id="tenant-123",
            operation=BulkOperation.QUERY,
            query=long_query,
            db_user="user",
            created_at=now,
            updated_at=now,
        )
        info = job.to_info()
        assert len(info.query) <= 103  # 100 chars + "..."
        assert info.query.endswith("...")

    def test_to_result(self) -> None:
        """Test conversion to BulkJobResult."""
        now = datetime.now(UTC)
        job = BulkJob(
            job_id="bulk-123",
            tenant_id="tenant-123",
            operation=BulkOperation.QUERY,
            query="SELECT * FROM users",
            db_user="user",
            created_at=now,
            updated_at=now,
            processing_started_at=now,
            completed_at=now,
            records_processed=1000,
            records_failed=5,
            bytes_processed=50000,
            files_count=2,
        )
        result = job.to_result(
            urls={"successful": "https://s3/success.csv"},
            url_expires=now,
        )
        assert result.number_records_processed == 1000
        assert result.number_records_failed == 5
        assert result.successful_results_url is not None

    def test_to_dynamo_item(self, sample_bulk_job: BulkJob) -> None:
        """Test conversion to DynamoDB item."""
        item = sample_bulk_job.to_dynamo_item()
        assert item["job_id"] == "bulk-abc123"
        assert item["tenant_id"] == "tenant-123"
        assert item["operation"] == "query"
        assert item["state"] == "InProgress"
        assert "created_at" in item

    def test_from_dynamo_item(self) -> None:
        """Test creation from DynamoDB item."""
        item = {
            "job_id": "bulk-xyz789",
            "tenant_id": "tenant-456",
            "operation": "query",
            "state": "JobComplete",
            "query": "SELECT COUNT(*) FROM orders",
            "content_type": "CSV",
            "compression": "GZIP",
            "db_user": "analyst",
            "created_at": "2024-01-15T10:00:00+00:00",
            "updated_at": "2024-01-15T10:05:00+00:00",
            "completed_at": "2024-01-15T10:05:00+00:00",
            "records_processed": 5000,
        }
        job = BulkJob.from_dynamo_item(item)
        assert job.job_id == "bulk-xyz789"
        assert job.state == BulkJobState.JOB_COMPLETE
        assert job.records_processed == 5000
        assert isinstance(job.created_at, datetime)
        assert isinstance(job.completed_at, datetime)

    def test_processing_time_calculation(self) -> None:
        """Test processing time calculation."""
        job = BulkJob(
            job_id="bulk-123",
            tenant_id="tenant-123",
            operation=BulkOperation.QUERY,
            query="SELECT 1",
            db_user="user",
            created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2024, 1, 1, 12, 0, 10, tzinfo=UTC),
            processing_started_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            completed_at=datetime(2024, 1, 1, 12, 0, 5, tzinfo=UTC),
        )
        result = job.to_result()
        assert result.total_processing_time_ms == 5000

    def test_processing_time_not_completed(self, sample_bulk_job: BulkJob) -> None:
        """Test processing time is 0 when not completed."""
        result = sample_bulk_job.to_result()
        assert result.total_processing_time_ms == 0

    def test_with_statement_ids(self) -> None:
        """Test job with Redshift statement IDs."""
        now = datetime.now(UTC)
        job = BulkJob(
            job_id="bulk-123",
            tenant_id="tenant-123",
            operation=BulkOperation.QUERY,
            query="SELECT * FROM users",
            db_user="user",
            created_at=now,
            updated_at=now,
            statement_ids=["stmt-1", "stmt-2"],
        )
        assert len(job.statement_ids) == 2

    def test_with_error_details(self) -> None:
        """Test job with error information."""
        now = datetime.now(UTC)
        job = BulkJob(
            job_id="bulk-123",
            tenant_id="tenant-123",
            operation=BulkOperation.INSERT,
            object="users",
            state=BulkJobState.FAILED,
            db_user="user",
            created_at=now,
            updated_at=now,
            error_message="Invalid data format",
            error_details={"row": 42, "column": "email", "error": "invalid format"},
        )
        assert job.error_message == "Invalid data format"
        assert job.error_details["row"] == 42

    def test_with_metadata(self) -> None:
        """Test job with custom metadata."""
        now = datetime.now(UTC)
        job = BulkJob(
            job_id="bulk-123",
            tenant_id="tenant-123",
            operation=BulkOperation.QUERY,
            query="SELECT 1",
            db_user="user",
            created_at=now,
            updated_at=now,
            metadata={"source": "api", "priority": "high"},
        )
        assert job.metadata["source"] == "api"

    def test_round_trip_serialization(self, sample_bulk_job: BulkJob) -> None:
        """Test serialization round trip."""
        item = sample_bulk_job.to_dynamo_item()
        restored = BulkJob.from_dynamo_item(item)
        assert restored.job_id == sample_bulk_job.job_id
        assert restored.tenant_id == sample_bulk_job.tenant_id
        assert restored.operation == sample_bulk_job.operation
        assert restored.state == sample_bulk_job.state
