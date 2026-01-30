"""Unit tests for job models.

Tests cover:
- JobStatus enum
- JobResult model
- JobError model
- Job model with DynamoDB serialization
- JobState lightweight model
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from spectra.models.job import Job, JobError, JobResult, JobStatus, JobState


class TestJobStatus:
    """Tests for JobStatus enum."""

    def test_status_values(self) -> None:
        """Test all status values exist."""
        statuses = [
            JobStatus.QUEUED,
            JobStatus.SUBMITTED,
            JobStatus.RUNNING,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.TIMEOUT,
        ]
        assert len(statuses) == 7

    def test_terminal_statuses(self) -> None:
        """Test terminal status detection."""
        assert JobStatus.COMPLETED.is_terminal is True
        assert JobStatus.FAILED.is_terminal is True
        assert JobStatus.CANCELLED.is_terminal is True
        assert JobStatus.TIMEOUT.is_terminal is True

        assert JobStatus.QUEUED.is_terminal is False
        assert JobStatus.SUBMITTED.is_terminal is False
        assert JobStatus.RUNNING.is_terminal is False


class TestJobResult:
    """Tests for JobResult model."""

    def test_valid_result(self) -> None:
        """Test creating valid job result."""
        result = JobResult(
            row_count=100,
            size_bytes=5000,
            location="s3://bucket/results/job-123.json",
            format="json",
        )
        assert result.row_count == 100
        assert result.size_bytes == 5000

    def test_inline_location(self) -> None:
        """Test inline result location."""
        result = JobResult(
            row_count=10,
            location="inline",
        )
        assert result.location == "inline"

    def test_with_columns(self) -> None:
        """Test result with column metadata."""
        result = JobResult(
            row_count=50,
            location="inline",
            columns=["id", "name", "email"],
            column_types=["integer", "varchar", "varchar"],
        )
        assert len(result.columns) == 3
        assert len(result.column_types) == 3

    def test_download_url(self) -> None:
        """Test result with presigned URL."""
        expires = datetime.now(UTC)
        result = JobResult(
            row_count=1000,
            location="s3://bucket/file.json",
            download_url="https://s3.amazonaws.com/bucket/file?sig=xxx",
            download_url_expires=expires,
        )
        assert result.download_url is not None
        assert result.download_url_expires == expires


class TestJobError:
    """Tests for JobError model."""

    def test_valid_error(self) -> None:
        """Test creating valid error."""
        error = JobError(
            code="QUERY_TIMEOUT",
            message="Query exceeded timeout limit",
        )
        assert error.code == "QUERY_TIMEOUT"
        assert error.message == "Query exceeded timeout limit"

    def test_error_with_details(self) -> None:
        """Test error with additional details."""
        error = JobError(
            code="SYNTAX_ERROR",
            message="Syntax error in SQL",
            details={"line": 10, "column": 5, "near": "WHERE"},
        )
        assert error.details["line"] == 10

    def test_redshift_error_code(self) -> None:
        """Test error with Redshift-specific code."""
        error = JobError(
            code="REDSHIFT_ERROR",
            message="Column not found",
            redshift_error_code="42703",
        )
        assert error.redshift_error_code == "42703"


class TestJob:
    """Tests for Job model."""

    @pytest.fixture
    def sample_job(self) -> Job:
        """Create sample job for testing."""
        now = datetime.now(UTC)
        return Job(
            job_id="job-abc123",
            tenant_id="tenant-123",
            status=JobStatus.QUEUED,
            sql="SELECT * FROM users",
            sql_hash="abc123def456",
            db_user="user_tenant_123",
            created_at=now,
            updated_at=now,
        )

    def test_job_creation(self, sample_job: Job) -> None:
        """Test job creation with required fields."""
        assert sample_job.job_id == "job-abc123"
        assert sample_job.status == JobStatus.QUEUED
        assert sample_job.async_mode is True

    def test_duration_calculation(self) -> None:
        """Test duration calculation."""
        now = datetime.now(UTC)
        job = Job(
            job_id="job-123",
            tenant_id="tenant-123",
            status=JobStatus.COMPLETED,
            sql="SELECT 1",
            sql_hash="hash",
            db_user="user",
            created_at=now,
            updated_at=now,
            started_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            completed_at=datetime(2024, 1, 1, 12, 0, 5, tzinfo=UTC),
        )
        assert job.duration_ms == 5000

    def test_duration_none_when_incomplete(self, sample_job: Job) -> None:
        """Test duration is None when not completed."""
        assert sample_job.duration_ms is None

    def test_wait_time_calculation(self) -> None:
        """Test wait time calculation."""
        job = Job(
            job_id="job-123",
            tenant_id="tenant-123",
            status=JobStatus.RUNNING,
            sql="SELECT 1",
            sql_hash="hash",
            db_user="user",
            created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime.now(UTC),
            started_at=datetime(2024, 1, 1, 12, 0, 10, tzinfo=UTC),
        )
        assert job.wait_time_ms == 10000

    def test_to_dynamo_item(self, sample_job: Job) -> None:
        """Test conversion to DynamoDB item."""
        item = sample_job.to_dynamo_item()
        assert item["job_id"] == "job-abc123"
        assert item["tenant_id"] == "tenant-123"
        assert item["status"] == "QUEUED"
        assert "created_at" in item

    def test_from_dynamo_item(self) -> None:
        """Test creation from DynamoDB item."""
        item = {
            "job_id": "job-xyz789",
            "tenant_id": "tenant-456",
            "status": "COMPLETED",
            "sql": "SELECT COUNT(*) FROM orders",
            "sql_hash": "xyz789",
            "db_user": "analyst",
            "created_at": "2024-01-15T10:00:00+00:00",
            "updated_at": "2024-01-15T10:01:00+00:00",
        }
        job = Job.from_dynamo_item(item)
        assert job.job_id == "job-xyz789"
        assert job.status == JobStatus.COMPLETED
        assert isinstance(job.created_at, datetime)

    def test_job_with_result(self) -> None:
        """Test job with result attached."""
        now = datetime.now(UTC)
        job = Job(
            job_id="job-123",
            tenant_id="tenant-123",
            status=JobStatus.COMPLETED,
            sql="SELECT 1",
            sql_hash="hash",
            db_user="user",
            created_at=now,
            updated_at=now,
            result=JobResult(row_count=100, location="inline"),
        )
        assert job.result is not None
        assert job.result.row_count == 100

    def test_job_with_error(self) -> None:
        """Test job with error attached."""
        now = datetime.now(UTC)
        job = Job(
            job_id="job-123",
            tenant_id="tenant-123",
            status=JobStatus.FAILED,
            sql="SELECT invalid_column FROM users",
            sql_hash="hash",
            db_user="user",
            created_at=now,
            updated_at=now,
            error=JobError(code="COLUMN_NOT_FOUND", message="Column not found"),
        )
        assert job.error is not None
        assert job.error.code == "COLUMN_NOT_FOUND"


class TestJobState:
    """Tests for JobState lightweight model."""

    def test_from_job(self) -> None:
        """Test creating JobState from Job."""
        now = datetime.now(UTC)
        job = Job(
            job_id="job-123",
            tenant_id="tenant-123",
            status=JobStatus.COMPLETED,
            sql="SELECT 1",
            sql_hash="hash",
            db_user="user",
            created_at=now,
            updated_at=now,
            completed_at=now,
            result=JobResult(row_count=50, location="s3://bucket/file.json"),
        )

        state = JobState.from_job(job)
        assert state.job_id == "job-123"
        assert state.status == JobStatus.COMPLETED
        assert state.row_count == 50
        assert state.result_location == "s3://bucket/file.json"

    def test_from_failed_job(self) -> None:
        """Test creating JobState from failed job."""
        now = datetime.now(UTC)
        job = Job(
            job_id="job-123",
            tenant_id="tenant-123",
            status=JobStatus.FAILED,
            sql="SELECT 1",
            sql_hash="hash",
            db_user="user",
            created_at=now,
            updated_at=now,
            error=JobError(code="ERROR", message="Something went wrong"),
        )

        state = JobState.from_job(job)
        assert state.status == JobStatus.FAILED
        assert state.error_message == "Something went wrong"
