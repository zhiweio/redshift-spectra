"""Unit tests for job service.

Tests for the JobService class that manages job state in DynamoDB.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from spectra.models.job import Job, JobError, JobResult, JobStatus
from spectra.services.job import (
    DuplicateJobError,
    JobNotFoundError,
    JobService,
)


# =============================================================================
# JobService Tests
# =============================================================================


class TestJobService:
    """Tests for JobService class."""

    @pytest.fixture
    def mock_dynamodb_table(self) -> MagicMock:
        """Create a mock DynamoDB table."""
        return MagicMock()

    @pytest.fixture
    def job_service(self, mock_dynamodb_table: MagicMock) -> JobService:
        """Create a JobService with mocked dependencies."""
        with patch("boto3.resource") as mock_resource:
            mock_resource.return_value.Table.return_value = mock_dynamodb_table
            service = JobService()
            service.table = mock_dynamodb_table
            return service

    def test_generate_job_id(self) -> None:
        """Test job ID generation format."""
        job_id = JobService.generate_job_id()

        assert job_id.startswith("job-")
        assert len(job_id) == 16  # "job-" + 12 hex chars

    def test_generate_job_id_uniqueness(self) -> None:
        """Test that job IDs are unique."""
        ids = {JobService.generate_job_id() for _ in range(100)}
        assert len(ids) == 100

    def test_hash_sql(self) -> None:
        """Test SQL hashing for deduplication."""
        sql1 = "SELECT * FROM table"
        sql2 = "SELECT  *  FROM  table"  # Same with extra whitespace
        sql3 = "SELECT id FROM table"

        hash1 = JobService.hash_sql(sql1)
        hash2 = JobService.hash_sql(sql2)
        hash3 = JobService.hash_sql(sql3)

        assert hash1 == hash2  # Same after normalization
        assert hash1 != hash3
        assert len(hash1) == 16

    def test_create_job(self, job_service: JobService, mock_dynamodb_table: MagicMock) -> None:
        """Test creating a new job."""
        mock_dynamodb_table.put_item.return_value = {}

        job = job_service.create_job(
            tenant_id="tenant-123",
            sql="SELECT * FROM sales LIMIT 100",
            db_user="user_tenant_123",
            db_group="analytics",
            output_format="json",
            async_mode=True,
        )

        assert job.job_id.startswith("job-")
        assert job.tenant_id == "tenant-123"
        assert job.status == JobStatus.QUEUED
        assert job.sql == "SELECT * FROM sales LIMIT 100"
        assert job.db_user == "user_tenant_123"
        mock_dynamodb_table.put_item.assert_called_once()

    def test_create_job_with_metadata(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test creating a job with custom metadata."""
        mock_dynamodb_table.put_item.return_value = {}

        job = job_service.create_job(
            tenant_id="tenant-123",
            sql="SELECT * FROM sales",
            db_user="user_tenant_123",
            metadata={"source": "dashboard", "user_id": "user-456"},
        )

        assert job.metadata == {"source": "dashboard", "user_id": "user-456"}

    def test_create_job_with_idempotency_key_duplicate(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test that duplicate idempotency keys raise error."""
        # Setup mock to return existing job
        existing_job_data = self._make_job_item("existing-job-123", "tenant-123")
        mock_dynamodb_table.query.return_value = {"Items": [existing_job_data]}

        with pytest.raises(DuplicateJobError) as exc_info:
            job_service.create_job(
                tenant_id="tenant-123",
                sql="SELECT * FROM sales",
                db_user="user_tenant_123",
                idempotency_key="unique-key-123",
            )

        assert exc_info.value.existing_job_id == "existing-job-123"

    def test_create_job_with_batch_id(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test creating a job with batch ID."""
        mock_dynamodb_table.put_item.return_value = {}

        job = job_service.create_job(
            tenant_id="tenant-123",
            sql="SELECT * FROM sales",
            db_user="user_tenant_123",
            batch_id="batch-456",
        )

        assert job.batch_id == "batch-456"

    def test_get_job_found(self, job_service: JobService, mock_dynamodb_table: MagicMock) -> None:
        """Test getting an existing job."""
        job_data = self._make_job_item("job-123", "tenant-123")
        mock_dynamodb_table.get_item.return_value = {"Item": job_data}

        job = job_service.get_job("job-123")

        assert job.job_id == "job-123"
        assert job.tenant_id == "tenant-123"

    def test_get_job_not_found(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test getting a non-existent job."""
        mock_dynamodb_table.get_item.return_value = {}

        with pytest.raises(JobNotFoundError):
            job_service.get_job("non-existent-job")

    def test_get_job_tenant_validation(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test that tenant ID is validated when provided."""
        job_data = self._make_job_item("job-123", "tenant-123")
        mock_dynamodb_table.get_item.return_value = {"Item": job_data}

        with pytest.raises(JobNotFoundError):
            job_service.get_job("job-123", tenant_id="different-tenant")

    def test_update_job_status_submitted(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test updating job status to SUBMITTED."""
        updated_job_data = self._make_job_item("job-123", "tenant-123")
        updated_job_data["status"] = "SUBMITTED"
        updated_job_data["statement_id"] = "stmt-456"
        mock_dynamodb_table.update_item.return_value = {"Attributes": updated_job_data}

        job = job_service.update_job_status(
            job_id="job-123",
            status=JobStatus.SUBMITTED,
            statement_id="stmt-456",
        )

        assert job.status == JobStatus.SUBMITTED
        mock_dynamodb_table.update_item.assert_called_once()

    def test_update_job_status_running(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test updating job status to RUNNING sets started_at."""
        updated_job_data = self._make_job_item("job-123", "tenant-123")
        updated_job_data["status"] = "RUNNING"
        updated_job_data["started_at"] = datetime.now(UTC).isoformat()
        mock_dynamodb_table.update_item.return_value = {"Attributes": updated_job_data}

        job_service.update_job_status(
            job_id="job-123",
            status=JobStatus.RUNNING,
        )

        call_args = mock_dynamodb_table.update_item.call_args
        update_expr = call_args.kwargs["UpdateExpression"]
        assert "started_at" in update_expr

    def test_update_job_status_completed(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test updating job status to COMPLETED with result."""
        updated_job_data = self._make_job_item("job-123", "tenant-123")
        updated_job_data["status"] = "COMPLETED"
        updated_job_data["completed_at"] = datetime.now(UTC).isoformat()
        mock_dynamodb_table.update_item.return_value = {"Attributes": updated_job_data}

        result = JobResult(
            row_count=100,
            location="s3://bucket/results/job-123.json",
            columns=["id", "name", "email", "status", "created_at"],
        )

        job_service.update_job_status(
            job_id="job-123",
            status=JobStatus.COMPLETED,
            result=result,
        )

        call_args = mock_dynamodb_table.update_item.call_args
        update_expr = call_args.kwargs["UpdateExpression"]
        assert "completed_at" in update_expr
        assert "result" in update_expr

    def test_update_job_status_failed(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test updating job status to FAILED with error."""
        updated_job_data = self._make_job_item("job-123", "tenant-123")
        updated_job_data["status"] = "FAILED"
        updated_job_data["completed_at"] = datetime.now(UTC).isoformat()
        mock_dynamodb_table.update_item.return_value = {"Attributes": updated_job_data}

        error = JobError(
            code="QUERY_ERROR",
            message="Invalid column reference",
            details={"column": "undefined_col"},
        )

        job_service.update_job_status(
            job_id="job-123",
            status=JobStatus.FAILED,
            error=error,
        )

        call_args = mock_dynamodb_table.update_item.call_args
        update_expr = call_args.kwargs["UpdateExpression"]
        assert "completed_at" in update_expr
        assert "error" in update_expr

    def test_list_jobs(self, job_service: JobService, mock_dynamodb_table: MagicMock) -> None:
        """Test listing jobs for a tenant."""
        job1 = self._make_job_item("job-1", "tenant-123")
        job2 = self._make_job_item("job-2", "tenant-123")
        mock_dynamodb_table.query.return_value = {
            "Items": [job1, job2],
            "LastEvaluatedKey": None,
        }

        jobs, next_key = job_service.list_jobs("tenant-123")

        assert len(jobs) == 2
        assert jobs[0].job_id == "job-1"
        assert jobs[1].job_id == "job-2"
        assert next_key is None

    def test_list_jobs_with_status_filter(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test listing jobs with status filter."""
        mock_dynamodb_table.query.return_value = {"Items": []}

        job_service.list_jobs("tenant-123", status=JobStatus.RUNNING)

        call_args = mock_dynamodb_table.query.call_args
        assert "FilterExpression" in call_args.kwargs

    def test_list_jobs_with_pagination(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test listing jobs with pagination."""
        job1 = self._make_job_item("job-1", "tenant-123")
        mock_dynamodb_table.query.return_value = {
            "Items": [job1],
            "LastEvaluatedKey": {"job_id": "job-1"},
        }

        jobs, next_key = job_service.list_jobs("tenant-123", limit=1)

        assert len(jobs) == 1
        assert next_key == {"job_id": "job-1"}

    def test_list_batch_jobs(self, job_service: JobService, mock_dynamodb_table: MagicMock) -> None:
        """Test listing jobs in a batch."""
        job1 = self._make_job_item("job-1", "tenant-123")
        job1["batch_id"] = "batch-456"
        job2 = self._make_job_item("job-2", "tenant-123")
        job2["batch_id"] = "batch-456"
        mock_dynamodb_table.query.return_value = {"Items": [job1, job2]}

        jobs = job_service.list_batch_jobs("batch-456", "tenant-123")

        assert len(jobs) == 2
        mock_dynamodb_table.query.assert_called_once()

    def test_get_pending_jobs(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test getting pending jobs."""
        job1 = self._make_job_item("job-1", "tenant-123")
        job1["status"] = "SUBMITTED"
        mock_dynamodb_table.scan.return_value = {"Items": [job1]}

        jobs = job_service.get_pending_jobs()

        assert len(jobs) == 1
        mock_dynamodb_table.scan.assert_called_once()

    def _make_job_item(self, job_id: str, tenant_id: str) -> dict[str, Any]:
        """Create a sample job item for testing."""
        now = datetime.now(UTC)
        return {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "status": "QUEUED",
            "sql": "SELECT * FROM test_table",
            "sql_hash": "abc123",
            "db_user": f"user_{tenant_id}",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "output_format": "json",
            "async_mode": True,
            "timeout_seconds": 900,
            "ttl": int(now.timestamp() + 86400 * 7),
        }


class TestJobServiceErrors:
    """Tests for JobService error handling."""

    @pytest.fixture
    def mock_dynamodb_table(self) -> MagicMock:
        """Create a mock DynamoDB table."""
        return MagicMock()

    @pytest.fixture
    def job_service(self, mock_dynamodb_table: MagicMock) -> JobService:
        """Create a JobService with mocked dependencies."""
        with patch("boto3.resource") as mock_resource:
            mock_resource.return_value.Table.return_value = mock_dynamodb_table
            service = JobService()
            service.table = mock_dynamodb_table
            return service

    def test_create_job_conditional_check_failure(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test handling of conditional check failure on create."""
        mock_dynamodb_table.query.return_value = {"Items": []}
        mock_dynamodb_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}},
            "PutItem",
        )

        with pytest.raises(DuplicateJobError):
            job_service.create_job(
                tenant_id="tenant-123",
                sql="SELECT * FROM sales",
                db_user="user_tenant_123",
            )

    def test_get_job_client_error(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test handling of client error on get."""
        mock_dynamodb_table.get_item.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Error"}},
            "GetItem",
        )

        with pytest.raises(ClientError):
            job_service.get_job("job-123")

    def test_update_job_status_client_error(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test handling of client error on update."""
        mock_dynamodb_table.update_item.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Error"}},
            "UpdateItem",
        )

        with pytest.raises(ClientError):
            job_service.update_job_status(
                job_id="job-123",
                status=JobStatus.RUNNING,
            )

    def test_list_jobs_client_error(
        self, job_service: JobService, mock_dynamodb_table: MagicMock
    ) -> None:
        """Test handling of client error on list."""
        mock_dynamodb_table.query.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Error"}},
            "Query",
        )

        with pytest.raises(ClientError):
            job_service.list_jobs("tenant-123")
