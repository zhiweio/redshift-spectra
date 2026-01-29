"""Query request and response models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class OutputFormat(str, Enum):
    """Output format options for query results."""

    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"


class QueryParameter(BaseModel):
    """A named parameter for SQL queries."""

    name: str = Field(..., description="Parameter name", min_length=1, max_length=128)
    value: str | int | float | bool | None = Field(..., description="Parameter value")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate parameter name format."""
        if not v.isidentifier():
            raise ValueError("Parameter name must be a valid identifier")
        return v


class QueryRequest(BaseModel):
    """Request model for submitting a query."""

    sql: str = Field(
        ...,
        description="SQL query to execute",
        min_length=1,
        max_length=100000,
    )
    parameters: list[QueryParameter] = Field(
        default_factory=list,
        description="Query parameters for parameterized queries",
        max_length=100,
    )
    output_format: OutputFormat = Field(
        default=OutputFormat.JSON,
        description="Desired output format",
    )
    async_mode: bool = Field(
        default=True,
        alias="async",
        description="Whether to execute asynchronously",
    )
    timeout_seconds: int | None = Field(
        default=None,
        description="Query timeout in seconds",
        ge=1,
        le=86400,
    )
    idempotency_key: str | None = Field(
        default=None,
        description="Idempotency key to prevent duplicate submissions",
        max_length=128,
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Custom metadata to attach to the job",
    )

    model_config = {"populate_by_name": True}

    @field_validator("sql")
    @classmethod
    def validate_sql(cls, v: str) -> str:
        """Basic SQL validation at model level.

        Note: Comprehensive security validation is performed by SQLValidator
        in the handler layer. This is just a quick sanity check.
        """
        v = v.strip()
        if not v:
            raise ValueError("SQL query cannot be empty")

        # Remove trailing semicolons (single statement only)
        v = v.rstrip(";").strip()

        # Quick check for obviously dangerous operations
        upper_sql = v.upper()

        # Must start with SELECT or WITH (for CTEs)
        if not (upper_sql.startswith("SELECT") or upper_sql.startswith("WITH")):
            raise ValueError("Only SELECT statements are allowed")

        # Block obviously dangerous patterns
        dangerous_patterns = [
            "DROP DATABASE",
            "DROP SCHEMA",
            "DROP TABLE",
            "TRUNCATE",
            "DELETE FROM",
            "INSERT INTO",
            "UPDATE ",
            "CREATE ",
            "ALTER ",
            "GRANT ",
            "REVOKE ",
        ]
        for pattern in dangerous_patterns:
            if pattern in upper_sql:
                raise ValueError(f"Dangerous SQL operation not allowed: {pattern.strip()}")

        return v


class QueryResponse(BaseModel):
    """Response model for query submission."""

    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Current job status")
    submitted_at: datetime = Field(..., description="Submission timestamp")
    tenant_id: str = Field(..., description="Tenant identifier")
    estimated_duration_seconds: int | None = Field(
        default=None,
        description="Estimated query duration",
    )
    poll_url: str | None = Field(
        default=None,
        description="URL to poll for status updates",
    )
    result_url: str | None = Field(
        default=None,
        description="URL to retrieve results when ready",
    )


class BulkQueryItem(BaseModel):
    """Single query item in a bulk request."""

    id: str = Field(
        ..., description="Client-provided query identifier", min_length=1, max_length=64
    )
    sql: str = Field(..., description="SQL query to execute", min_length=1, max_length=100000)
    parameters: list[QueryParameter] = Field(
        default_factory=list,
        description="Query parameters",
    )
    priority: int = Field(
        default=0, description="Query priority (higher = more urgent)", ge=0, le=100
    )


class BulkQueryRequest(BaseModel):
    """Request model for submitting multiple queries."""

    queries: list[BulkQueryItem] = Field(
        ...,
        description="List of queries to execute",
        min_length=1,
        max_length=100,
    )
    parallel: bool = Field(
        default=True,
        description="Whether to execute queries in parallel",
    )
    max_concurrency: int = Field(
        default=5,
        description="Maximum concurrent query executions",
        ge=1,
        le=20,
    )
    output_format: OutputFormat = Field(
        default=OutputFormat.JSON,
        description="Output format for all query results",
    )
    fail_fast: bool = Field(
        default=False,
        description="Stop on first failure",
    )
    idempotency_key: str | None = Field(
        default=None,
        description="Idempotency key for the bulk operation",
        max_length=128,
    )


class BulkQueryResponse(BaseModel):
    """Response model for bulk query submission."""

    batch_id: str = Field(..., description="Unique batch identifier")
    total_queries: int = Field(..., description="Total number of queries submitted")
    jobs: list[QueryResponse] = Field(..., description="Individual job responses")
    submitted_at: datetime = Field(..., description="Batch submission timestamp")
    status_url: str | None = Field(
        default=None,
        description="URL to check batch status",
    )


class ResultMetadata(BaseModel):
    """Metadata for query results."""

    columns: list[str] = Field(..., description="Column names")
    column_types: list[str] | None = Field(default=None, description="Column data types")
    row_count: int = Field(..., description="Total row count", ge=0)
    size_bytes: int | None = Field(default=None, description="Result size in bytes")
    truncated: bool = Field(default=False, description="Whether results were truncated")
    execution_time_ms: int | None = Field(default=None, description="Query execution time")


class QueryResultResponse(BaseModel):
    """Response model for query results."""

    job_id: str = Field(..., description="Job identifier")
    status: str = Field(..., description="Job status")
    data: list[dict[str, Any]] | None = Field(
        default=None,
        description="Result data (for inline results)",
    )
    download_url: str | None = Field(
        default=None,
        description="Presigned URL for large results",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Download URL expiration time",
    )
    format: OutputFormat = Field(..., description="Result format")
    metadata: ResultMetadata | None = Field(default=None, description="Result metadata")
