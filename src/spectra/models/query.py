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
    """Request model for submitting a synchronous query.

    This endpoint is designed for small-to-medium result sets with quick responses.
    For large datasets or long-running queries, use the /v1/bulk API instead.
    """

    sql: str = Field(
        ...,
        description="SQL query to execute (SELECT only)",
        min_length=1,
        max_length=100000,
    )
    parameters: list[QueryParameter] = Field(
        default_factory=list,
        description="Query parameters for parameterized queries",
        max_length=100,
    )
    timeout_seconds: int = Field(
        default=60,
        description="Query timeout in seconds (max 300)",
        ge=1,
        le=300,
    )
    idempotency_key: str | None = Field(
        default=None,
        description="Idempotency key to prevent duplicate submissions",
        max_length=128,
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Custom metadata to attach to the job for audit purposes",
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


class ResultMetadata(BaseModel):
    """Metadata for query results."""

    columns: list[dict[str, Any]] = Field(..., description="Column definitions with name and type")
    row_count: int = Field(..., description="Number of rows returned", ge=0)
    truncated: bool = Field(
        default=False, description="Whether results were truncated due to size limit"
    )
    execution_time_ms: int | None = Field(
        default=None, description="Query execution time in milliseconds"
    )
    message: str | None = Field(
        default=None, description="Additional message (e.g., truncation warning)"
    )


class QueryResponse(BaseModel):
    """Response model for synchronous query execution.

    Returns inline data for small result sets, or partial data with truncation
    warning for larger datasets.
    """

    job_id: str = Field(..., description="Unique job identifier (for audit trail)")
    status: str = Field(..., description="Query status: COMPLETED, FAILED, or TIMEOUT")
    data: list[dict[str, Any]] | None = Field(
        default=None,
        description="Query results as JSON array",
    )
    metadata: ResultMetadata | None = Field(
        default=None,
        description="Result metadata including columns and row count",
    )
    error: dict[str, Any] | None = Field(
        default=None,
        description="Error details if query failed",
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
    submitted_at: datetime = Field(..., description="Batch submission timestamp")
    status_url: str | None = Field(
        default=None,
        description="URL to check batch status",
    )


class QueryResultResponse(BaseModel):
    """Response model for query results (used by result handler)."""

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
    format: OutputFormat = Field(default=OutputFormat.JSON, description="Result format")
    metadata: ResultMetadata | None = Field(default=None, description="Result metadata")
