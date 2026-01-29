"""Job state models for query tracking."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Job execution status."""

    QUEUED = "QUEUED"
    SUBMITTED = "SUBMITTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"

    @property
    def is_terminal(self) -> bool:
        """Check if status is terminal (no further changes expected)."""
        return self in {
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.TIMEOUT,
        }


class JobResult(BaseModel):
    """Result information for a completed job."""

    row_count: int = Field(..., description="Number of rows returned", ge=0)
    size_bytes: int | None = Field(default=None, description="Result size in bytes")
    columns: list[str] = Field(default_factory=list, description="Column names")
    column_types: list[str] = Field(default_factory=list, description="Column data types")
    location: str = Field(..., description="Result location: 'inline' or S3 path")
    format: str = Field(default="json", description="Result format")
    download_url: str | None = Field(default=None, description="Presigned download URL")
    download_url_expires: datetime | None = Field(default=None, description="URL expiration")


class JobError(BaseModel):
    """Error information for a failed job."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: dict[str, Any] | None = Field(default=None, description="Additional error details")
    redshift_error_code: str | None = Field(
        default=None, description="Redshift-specific error code"
    )


class Job(BaseModel):
    """Job state model for DynamoDB persistence."""

    job_id: str = Field(..., description="Unique job identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    status: JobStatus = Field(..., description="Current job status")
    sql: str = Field(..., description="SQL query")
    sql_hash: str = Field(..., description="Hash of SQL for deduplication")
    db_user: str = Field(..., description="Redshift database user")
    db_group: str | None = Field(default=None, description="Redshift database group")

    # Timestamps
    created_at: datetime = Field(..., description="Job creation time")
    updated_at: datetime = Field(..., description="Last update time")
    submitted_at: datetime | None = Field(default=None, description="Time submitted to Redshift")
    started_at: datetime | None = Field(default=None, description="Execution start time")
    completed_at: datetime | None = Field(default=None, description="Completion time")

    # Redshift Data API tracking
    statement_id: str | None = Field(default=None, description="Redshift Data API statement ID")

    # Result information
    result: JobResult | None = Field(default=None, description="Result info for completed jobs")
    error: JobError | None = Field(default=None, description="Error info for failed jobs")

    # Configuration
    output_format: str = Field(default="json", description="Requested output format")
    timeout_seconds: int | None = Field(default=None, description="Query timeout")
    async_mode: bool = Field(default=True, description="Async execution mode")

    # Metadata
    idempotency_key: str | None = Field(default=None, description="Idempotency key")
    batch_id: str | None = Field(default=None, description="Batch ID for bulk operations")
    metadata: dict[str, Any] | None = Field(default=None, description="Custom metadata")

    # TTL for DynamoDB
    ttl: int | None = Field(default=None, description="TTL epoch timestamp for DynamoDB")

    model_config = {"use_enum_values": True}

    @property
    def duration_ms(self) -> int | None:
        """Calculate job duration in milliseconds."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None

    @property
    def wait_time_ms(self) -> int | None:
        """Calculate wait time before execution started."""
        if self.created_at and self.started_at:
            delta = self.started_at - self.created_at
            return int(delta.total_seconds() * 1000)
        return None

    def to_dynamo_item(self) -> dict[str, Any]:
        """Convert to DynamoDB item format."""
        item = self.model_dump(mode="json", exclude_none=True)

        # Convert datetime to ISO strings
        for key in ["created_at", "updated_at", "submitted_at", "started_at", "completed_at"]:
            if item.get(key) and isinstance(item[key], datetime):
                item[key] = item[key].isoformat()

        return item

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Job":
        """Create Job from DynamoDB item."""
        # Parse datetime strings
        for key in ["created_at", "updated_at", "submitted_at", "started_at", "completed_at"]:
            if item.get(key) and isinstance(item[key], str):
                item[key] = datetime.fromisoformat(item[key])

        # Handle nested result/error
        if (
            item.get("result")
            and "download_url_expires" in item["result"]
            and item["result"]["download_url_expires"]
            and isinstance(item["result"]["download_url_expires"], str)
        ):
            item["result"]["download_url_expires"] = datetime.fromisoformat(
                item["result"]["download_url_expires"]
            )

        return cls.model_validate(item)


class JobState(BaseModel):
    """Lightweight job state for status responses."""

    job_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    row_count: int | None = None
    result_location: str | None = None
    error_message: str | None = None

    @classmethod
    def from_job(cls, job: Job) -> "JobState":
        """Create JobState from full Job model."""
        return cls(
            job_id=job.job_id,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
            row_count=job.result.row_count if job.result else None,
            result_location=job.result.location if job.result else None,
            error_message=job.error.message if job.error else None,
        )
