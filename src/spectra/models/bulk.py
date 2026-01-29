"""Bulk API models following Salesforce Bulk v2 design patterns.

This module implements a Bulk API for large-scale data import/export operations,
inspired by Salesforce Bulk API v2 design principles.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class BulkOperation(str, Enum):
    """Bulk operation types."""

    QUERY = "query"  # Export data via SQL query
    INSERT = "insert"  # Insert new records
    UPDATE = "update"  # Update existing records
    UPSERT = "upsert"  # Insert or update records
    DELETE = "delete"  # Delete records


class BulkJobState(str, Enum):
    """Bulk job state machine (Salesforce Bulk v2 compatible).

    State transitions:
    - Open -> UploadComplete (client finishes upload)
    - UploadComplete -> InProgress (processing starts)
    - InProgress -> JobComplete (success)
    - InProgress -> Failed (error)
    - Any non-terminal -> Aborted (user cancellation)
    """

    OPEN = "Open"  # Job created, awaiting data upload
    UPLOAD_COMPLETE = "UploadComplete"  # Upload finished, ready for processing
    IN_PROGRESS = "InProgress"  # Processing data
    JOB_COMPLETE = "JobComplete"  # Successfully completed
    FAILED = "Failed"  # Failed with errors
    ABORTED = "Aborted"  # Cancelled by user

    @property
    def is_terminal(self) -> bool:
        """Check if state is terminal."""
        return self in {
            BulkJobState.JOB_COMPLETE,
            BulkJobState.FAILED,
            BulkJobState.ABORTED,
        }


class DataFormat(str, Enum):
    """Supported data formats for import/export."""

    CSV = "CSV"
    JSON = "JSON"
    PARQUET = "PARQUET"


class CompressionType(str, Enum):
    """Supported compression types (Redshift native)."""

    NONE = "NONE"
    GZIP = "GZIP"
    LZOP = "LZOP"
    BZIP2 = "BZIP2"
    ZSTD = "ZSTD"


class LineEnding(str, Enum):
    """Line ending options for CSV."""

    LF = "LF"
    CRLF = "CRLF"


# =============================================================================
# Request Models
# =============================================================================


class ColumnMapping(BaseModel):
    """Column mapping for import operations."""

    source_column: str = Field(..., description="Column name in source data")
    target_column: str = Field(..., description="Column name in target table")
    transform: str | None = Field(default=None, description="SQL expression for transformation")


class BulkJobCreateRequest(BaseModel):
    """Request model for creating a bulk job.

    For QUERY operations:
        - Provide `query` with the SQL SELECT statement
        - Data will be exported to S3 in the specified format

    For INSERT/UPDATE/UPSERT/DELETE operations:
        - Provide `object` (table name) and `external_id_field` (for upsert)
        - Upload data via the returned content URL
    """

    operation: BulkOperation = Field(..., description="Type of bulk operation")

    # For export (query) operations
    query: str | None = Field(
        default=None,
        description="SQL query for export operations",
        max_length=100000,
    )

    # For import operations
    object: str | None = Field(
        default=None,
        description="Target table name for import operations",
        max_length=256,
    )
    external_id_field: str | None = Field(
        default=None,
        description="Column for matching records in upsert/update operations",
    )
    column_mappings: list[ColumnMapping] | None = Field(
        default=None,
        description="Column mappings for import",
    )

    # Format configuration
    content_type: DataFormat = Field(
        default=DataFormat.CSV,
        description="Data format for input/output",
    )
    compression: CompressionType = Field(
        default=CompressionType.GZIP,
        description="Compression type for files",
    )
    line_ending: LineEnding = Field(
        default=LineEnding.LF,
        description="Line ending for CSV files",
    )
    column_delimiter: str = Field(
        default=",",
        description="Column delimiter for CSV",
        max_length=1,
    )

    # Optional settings
    assignment_rule_id: str | None = Field(
        default=None,
        description="Custom assignment rule for import",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str | None, info) -> str | None:  # noqa: ARG003
        """Validate query is provided for query operations."""
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Query cannot be empty")
            # Basic validation for SELECT
            if not v.upper().startswith("SELECT"):
                raise ValueError("Export query must be a SELECT statement")
        return v

    @field_validator("object")
    @classmethod
    def validate_object(cls, v: str | None) -> str | None:
        """Validate table name."""
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Object (table name) cannot be empty")
            # Basic SQL injection prevention
            if ";" in v or "--" in v:
                raise ValueError("Invalid table name")
        return v


class BulkJobUpdateRequest(BaseModel):
    """Request model for updating a bulk job state."""

    state: Literal["UploadComplete", "Aborted"] = Field(
        ...,
        description="New state: 'UploadComplete' or 'Aborted'",
    )


# =============================================================================
# Response Models
# =============================================================================


class BulkJobInfo(BaseModel):
    """Bulk job information response."""

    id: str = Field(..., description="Unique job identifier")
    operation: BulkOperation = Field(..., description="Type of operation")
    state: BulkJobState = Field(..., description="Current job state")
    object: str | None = Field(default=None, description="Target table name")
    query: str | None = Field(default=None, description="Export query (masked)")

    # Format settings
    content_type: DataFormat = Field(..., description="Data format")
    compression: CompressionType = Field(..., description="Compression type")
    line_ending: LineEnding | None = Field(default=None, description="Line ending")
    column_delimiter: str | None = Field(default=None, description="Column delimiter")

    # URLs for data upload/download
    content_url: str | None = Field(
        default=None,
        description="URL for uploading data (import) or downloading results (export)",
    )
    content_url_expires_at: datetime | None = Field(
        default=None,
        description="URL expiration time",
    )

    # Timestamps
    created_at: datetime = Field(..., description="Job creation time")
    created_by_id: str = Field(..., description="Tenant/user who created the job")
    system_modstamp: datetime = Field(..., description="Last modification time")

    # Job progress (for completed jobs)
    job_type: str = Field(default="V2Ingest", description="Job type identifier")
    api_version: str = Field(default="v1", description="API version")
    concurrency_mode: str = Field(default="Parallel", description="Concurrency mode")

    # Error info
    error_message: str | None = Field(default=None, description="Error message if failed")

    model_config = {"use_enum_values": True}


class BulkJobResult(BaseModel):
    """Result information for a completed bulk job."""

    # Processing statistics
    number_records_processed: int = Field(default=0, description="Total records processed")
    number_records_failed: int = Field(default=0, description="Records that failed processing")
    total_processing_time_ms: int = Field(
        default=0, description="Total processing time in milliseconds"
    )

    # For export jobs
    result_files: list[str] = Field(
        default_factory=list,
        description="List of result file paths in S3",
    )
    result_file_count: int = Field(default=0, description="Number of result files")
    total_size_bytes: int = Field(default=0, description="Total size of result files")

    # Download URLs
    successful_results_url: str | None = Field(
        default=None,
        description="URL to download successful results",
    )
    failed_results_url: str | None = Field(
        default=None,
        description="URL to download failed record details",
    )
    unprocessed_records_url: str | None = Field(
        default=None,
        description="URL to download unprocessed records",
    )

    # URL expiration
    urls_expire_at: datetime | None = Field(
        default=None,
        description="Expiration time for download URLs",
    )


class BulkJobResponse(BaseModel):
    """Complete bulk job response with info and results."""

    info: BulkJobInfo
    results: BulkJobResult | None = None


class BulkJobListResponse(BaseModel):
    """Response for listing bulk jobs."""

    done: bool = Field(..., description="Whether all jobs have been returned")
    records: list[BulkJobInfo] = Field(..., description="List of jobs")
    next_records_url: str | None = Field(
        default=None,
        description="URL to fetch next page of results",
    )
    total_size: int = Field(..., description="Total number of jobs")


# =============================================================================
# DynamoDB Model
# =============================================================================


class BulkJob(BaseModel):
    """Bulk job model for DynamoDB persistence."""

    job_id: str = Field(..., description="Unique job identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    operation: BulkOperation = Field(..., description="Type of operation")
    state: BulkJobState = Field(default=BulkJobState.OPEN, description="Current state")

    # Target/query
    object: str | None = Field(default=None, description="Target table name")
    query: str | None = Field(default=None, description="SQL query for exports")
    external_id_field: str | None = Field(default=None, description="External ID field")
    column_mappings: list[dict[str, Any]] | None = Field(
        default=None, description="Column mappings"
    )

    # Format configuration
    content_type: DataFormat = Field(default=DataFormat.CSV, description="Data format")
    compression: CompressionType = Field(
        default=CompressionType.GZIP, description="Compression type"
    )
    line_ending: LineEnding = Field(default=LineEnding.LF, description="Line ending")
    column_delimiter: str = Field(default=",", description="Column delimiter")

    # Database context
    db_user: str = Field(..., description="Redshift database user")
    db_group: str | None = Field(default=None, description="Redshift database group")

    # S3 locations
    s3_input_prefix: str | None = Field(default=None, description="S3 prefix for input data")
    s3_output_prefix: str | None = Field(default=None, description="S3 prefix for output data")
    s3_manifest_key: str | None = Field(default=None, description="S3 key for manifest file")

    # Redshift tracking
    statement_ids: list[str] = Field(
        default_factory=list, description="Redshift Data API statement IDs"
    )

    # Processing statistics
    records_processed: int = Field(default=0, description="Records processed")
    records_failed: int = Field(default=0, description="Records failed")
    bytes_processed: int = Field(default=0, description="Bytes processed")
    files_count: int = Field(default=0, description="Number of files")

    # Timestamps
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Last update time")
    upload_completed_at: datetime | None = Field(default=None, description="Upload completion time")
    processing_started_at: datetime | None = Field(
        default=None, description="Processing start time"
    )
    completed_at: datetime | None = Field(default=None, description="Completion time")

    # Error information
    error_message: str | None = Field(default=None, description="Error message")
    error_details: dict[str, Any] | None = Field(default=None, description="Detailed error info")

    # TTL for DynamoDB
    ttl: int | None = Field(default=None, description="TTL epoch timestamp")

    # Metadata
    metadata: dict[str, Any] | None = Field(default=None, description="Custom metadata")

    model_config = {"use_enum_values": True}

    def to_info(
        self, content_url: str | None = None, url_expires: datetime | None = None
    ) -> BulkJobInfo:
        """Convert to BulkJobInfo response."""
        return BulkJobInfo(
            id=self.job_id,
            operation=self.operation,
            state=self.state,
            object=self.object,
            query=self._mask_query(self.query) if self.query else None,
            content_type=self.content_type,
            compression=self.compression,
            line_ending=self.line_ending if self.content_type == DataFormat.CSV else None,
            column_delimiter=self.column_delimiter if self.content_type == DataFormat.CSV else None,
            content_url=content_url,
            content_url_expires_at=url_expires,
            created_at=self.created_at,
            created_by_id=self.tenant_id,
            system_modstamp=self.updated_at,
            error_message=self.error_message,
        )

    def to_result(
        self, urls: dict[str, str] | None = None, url_expires: datetime | None = None
    ) -> BulkJobResult:
        """Convert to BulkJobResult."""
        return BulkJobResult(
            number_records_processed=self.records_processed,
            number_records_failed=self.records_failed,
            total_processing_time_ms=self._calculate_processing_time(),
            result_file_count=self.files_count,
            total_size_bytes=self.bytes_processed,
            successful_results_url=urls.get("successful") if urls else None,
            failed_results_url=urls.get("failed") if urls else None,
            unprocessed_records_url=urls.get("unprocessed") if urls else None,
            urls_expire_at=url_expires,
        )

    @staticmethod
    def _mask_query(query: str) -> str:
        """Mask sensitive parts of query for response."""
        if len(query) > 100:
            return query[:100] + "..."
        return query

    def _calculate_processing_time(self) -> int:
        """Calculate processing time in milliseconds."""
        if self.processing_started_at and self.completed_at:
            delta = self.completed_at - self.processing_started_at
            return int(delta.total_seconds() * 1000)
        return 0

    def to_dynamo_item(self) -> dict[str, Any]:
        """Convert to DynamoDB item format."""
        item = self.model_dump(mode="json", exclude_none=True)

        # Datetime fields to convert
        datetime_fields = [
            "created_at",
            "updated_at",
            "upload_completed_at",
            "processing_started_at",
            "completed_at",
        ]
        for key in datetime_fields:
            if item.get(key) and isinstance(item[key], datetime):
                item[key] = item[key].isoformat()

        return item

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "BulkJob":
        """Create BulkJob from DynamoDB item."""
        datetime_fields = [
            "created_at",
            "updated_at",
            "upload_completed_at",
            "processing_started_at",
            "completed_at",
        ]
        for key in datetime_fields:
            if key in item and item[key] and isinstance(item[key], str):
                item[key] = datetime.fromisoformat(item[key])

        return cls.model_validate(item)
