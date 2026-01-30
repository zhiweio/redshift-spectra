"""Query submission Lambda handler.

This handler provides synchronous query execution for small-to-medium result sets.
For large datasets or long-running queries, use the /v1/bulk API instead.
"""

import time
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.exceptions import (
    BadRequestError,
    InternalServerError,
    UnauthorizedError,
)
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import ValidationError

from spectra.middleware.tenant import TenantContext, extract_tenant_context
from spectra.models.query import QueryRequest, QueryResponse, ResultMetadata
from spectra.services.job import DuplicateJobError, JobService
from spectra.services.redshift import (
    QueryExecutionError,
    QueryTimeoutError,
    RedshiftService,
)
from spectra.utils.config import get_settings
from spectra.utils.response import api_response
from spectra.utils.sql_validator import (
    SQLSecurityLevel,
    SQLValidationError,
    SQLValidator,
    inject_limit,
)

logger = Logger()
tracer = Tracer()
metrics = Metrics()
app = APIGatewayRestResolver()


def _get_sql_validator() -> SQLValidator:
    """Get SQL validator with configured settings."""
    settings = get_settings()
    security_level = SQLSecurityLevel(settings.sql_security_level)
    return SQLValidator(
        security_level=security_level,
        max_query_length=settings.sql_max_query_length,
        max_joins=settings.sql_max_joins,
        max_subqueries=settings.sql_max_subqueries,
        allow_cte=settings.sql_allow_cte,
        allow_union=settings.sql_allow_union,
    )


@app.post("/v1/queries")
@tracer.capture_method
def submit_query() -> Response:
    """Submit a query for synchronous execution.

    This endpoint executes queries synchronously and returns results inline.
    - Maximum timeout: 300 seconds (5 minutes)
    - Results are limited to prevent memory issues
    - For large datasets, use POST /v1/bulk instead

    Returns:
        Query results with data and metadata
    """
    settings = get_settings()
    start_time = time.time()

    # Extract tenant context
    try:
        tenant_ctx: TenantContext = extract_tenant_context(app.current_event)
    except ValueError as e:
        raise UnauthorizedError(str(e))

    logger.append_keys(tenant_id=tenant_ctx.tenant_id)

    # Parse and validate request
    try:
        body = app.current_event.json_body
        request = QueryRequest.model_validate(body)
    except ValidationError as e:
        raise BadRequestError(f"Invalid request: {e.errors()}")
    except Exception as e:
        raise BadRequestError(f"Invalid JSON body: {e!s}")

    # Validate SQL for security
    try:
        sql_validator = _get_sql_validator()
        validation_result = sql_validator.validate(request.sql)
        if validation_result.warnings:
            logger.warning(
                "SQL validation warnings",
                extra={"warnings": validation_result.warnings},
            )
    except SQLValidationError as e:
        logger.warning(
            "SQL validation failed",
            extra={
                "error_code": e.error_code,
                "message": e.message,
                "details": e.details,
            },
        )
        metrics.add_metric(name="SQLValidationFailed", unit=MetricUnit.Count, value=1)
        raise BadRequestError(f"SQL validation failed: {e.message}")

    # Inject LIMIT to prevent oversized result sets
    max_rows = settings.result_size_threshold
    limited_sql, original_limit = inject_limit(request.sql, max_rows)

    logger.info(
        "Injected LIMIT clause",
        extra={
            "original_limit": original_limit,
            "enforced_limit": max_rows + 1,
            "sql_modified": limited_sql != request.sql,
        },
    )

    # Initialize services
    job_service = JobService()
    redshift_service = RedshiftService()

    job = None
    statement_id = None

    try:
        # Create job record for audit trail
        job = job_service.create_job(
            tenant_id=tenant_ctx.tenant_id,
            sql=request.sql,  # Store original SQL for audit
            db_user=tenant_ctx.db_user,
            db_group=tenant_ctx.db_group,
            output_format="json",  # Always JSON for query endpoint
            async_mode=False,  # Synchronous execution
            timeout_seconds=request.timeout_seconds,
            idempotency_key=request.idempotency_key,
            metadata=request.metadata,
        )

        logger.append_keys(job_id=job.job_id)

        # Submit to Redshift Data API (with modified SQL including LIMIT)
        statement_id = redshift_service.execute_statement(
            sql=limited_sql,
            db_user=tenant_ctx.db_user,
            tenant_id=tenant_ctx.tenant_id,
            statement_name=job.job_id,
            with_event=False,  # No async events needed
        )

        # Update job with statement ID
        job_service.update_job_submitted(job.job_id, statement_id)

        # Wait for query completion (synchronous polling)
        description = redshift_service.wait_for_statement(
            statement_id=statement_id,
            timeout_seconds=request.timeout_seconds,
        )

        # Fetch results with pagination
        result = redshift_service.get_all_statement_results(
            statement_id=statement_id,
            max_rows=max_rows + 1,  # +1 for truncation detection
        )

        columns = result.get("columns", [])
        records = result.get("records", [])
        total_fetched = len(records)

        # Check if results were truncated
        truncated = total_fetched > max_rows
        if truncated:
            records = records[:max_rows]  # Return only max_rows
            message = (
                f"Result exceeds limit of {max_rows} rows. "
                f"Only first {max_rows} rows returned. "
                "For complete results, use POST /v1/bulk API."
            )
            logger.info(
                "Results truncated",
                extra={"fetched": total_fetched, "returned": max_rows},
            )
        else:
            message = None

        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)

        # Update job status to completed
        job_service.update_job_status(
            job_id=job.job_id,
            status="COMPLETED",
            result_rows=len(records),
            duration_ms=execution_time_ms,
        )

        # Build response
        metadata = ResultMetadata(
            columns=columns,
            row_count=len(records),
            truncated=truncated,
            execution_time_ms=execution_time_ms,
            message=message,
        )

        response = QueryResponse(
            job_id=job.job_id,
            status="COMPLETED",
            data=records,
            metadata=metadata,
        )

        metrics.add_metric(name="QueryCompleted", unit=MetricUnit.Count, value=1)
        metrics.add_metric(
            name="QueryExecutionTime", unit=MetricUnit.Milliseconds, value=execution_time_ms
        )
        if truncated:
            metrics.add_metric(name="QueryTruncated", unit=MetricUnit.Count, value=1)

        return api_response(200, response.model_dump(mode="json"))

    except DuplicateJobError as e:
        logger.info("Duplicate job detected", extra={"existing_job_id": e.existing_job_id})
        # For sync queries, just return conflict error
        raise BadRequestError(
            f"Duplicate query detected. Use different idempotency_key or wait for job {e.existing_job_id}"
        )

    except QueryTimeoutError as e:
        logger.warning("Query timed out", extra={"timeout": request.timeout_seconds})
        metrics.add_metric(name="QueryTimeout", unit=MetricUnit.Count, value=1)

        # Update job status
        if job:
            job_service.update_job_status(job.job_id, status="TIMEOUT")

        response = QueryResponse(
            job_id=job.job_id if job else "unknown",
            status="TIMEOUT",
            error={
                "code": "QUERY_TIMEOUT",
                "message": f"Query exceeded timeout of {request.timeout_seconds} seconds. "
                "For long-running queries, use POST /v1/bulk API.",
            },
        )
        return api_response(408, response.model_dump(mode="json"))

    except QueryExecutionError as e:
        logger.error("Query execution failed", extra={"error": str(e)})
        metrics.add_metric(name="QueryFailed", unit=MetricUnit.Count, value=1)

        # Update job status
        if job:
            job_service.update_job_status(
                job.job_id,
                status="FAILED",
                error_code=e.code,
                error_message=str(e),
            )

        response = QueryResponse(
            job_id=job.job_id if job else "unknown",
            status="FAILED",
            error={
                "code": e.code or "QUERY_FAILED",
                "message": str(e),
            },
        )
        return api_response(500, response.model_dump(mode="json"))

    except Exception as e:
        logger.exception("Unexpected error during query execution")
        metrics.add_metric(name="QueryError", unit=MetricUnit.Count, value=1)

        if job:
            job_service.update_job_status(
                job.job_id,
                status="FAILED",
                error_code="INTERNAL_ERROR",
                error_message=str(e),
            )

        raise InternalServerError(f"Failed to execute query: {e}")


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for query submission."""
    return app.resolve(event, context)
