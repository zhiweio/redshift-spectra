"""Query submission Lambda handler."""

from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
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
from spectra.models.query import QueryRequest, QueryResponse
from spectra.services.job import DuplicateJobError, JobService
from spectra.services.redshift import QueryExecutionError, RedshiftService
from spectra.utils.config import get_settings
from spectra.utils.response import api_response
from spectra.utils.sql_validator import SQLSecurityLevel, SQLValidationError, SQLValidator

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
def submit_query() -> dict[str, Any]:
    """Submit a query for execution.

    Returns:
        Query submission response with job ID
    """
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

    # Initialize services
    job_service = JobService()
    redshift_service = RedshiftService()

    try:
        # Create job record
        job = job_service.create_job(
            tenant_id=tenant_ctx.tenant_id,
            sql=request.sql,
            db_user=tenant_ctx.db_user,
            db_group=tenant_ctx.db_group,
            output_format=request.output_format.value,
            async_mode=request.async_mode,
            timeout_seconds=request.timeout_seconds,
            idempotency_key=request.idempotency_key,
            metadata=request.metadata,
        )

        # Submit to Redshift Data API with session reuse
        statement_id = redshift_service.execute_statement(
            sql=request.sql,
            db_user=tenant_ctx.db_user,
            tenant_id=tenant_ctx.tenant_id,  # Enable session reuse per tenant
            statement_name=job.job_id,
            with_event=True,  # Enable CloudWatch events for async processing
        )

        # Update job with statement ID
        job_service.update_job_submitted(job.job_id, statement_id)

        # Record metrics
        metrics.add_metric(name="QuerySubmitted", unit=MetricUnit.Count, value=1)
        metrics.add_metadata(key="tenant_id", value=tenant_ctx.tenant_id)

        logger.info(
            "Query submitted successfully",
            extra={
                "job_id": job.job_id,
                "statement_id": statement_id,
                "async_mode": request.async_mode,
            },
        )

        # Build response
        response = QueryResponse(
            job_id=job.job_id,
            status=job.status.value,
            submitted_at=job.created_at,
            tenant_id=tenant_ctx.tenant_id,
            estimated_duration_seconds=30,  # Default estimate
        )

        return api_response(201, response.model_dump(mode="json"))

    except DuplicateJobError as e:
        logger.info("Duplicate job detected", extra={"existing_job_id": e.existing_job_id})
        # Return existing job info
        existing_job = job_service.get_job(e.existing_job_id)
        response = QueryResponse(
            job_id=existing_job.job_id,
            status=existing_job.status.value,
            submitted_at=existing_job.created_at,
            tenant_id=tenant_ctx.tenant_id,
        )
        return api_response(200, response.model_dump(mode="json"))

    except QueryExecutionError as e:
        logger.error("Query execution failed", extra={"error": str(e)})
        metrics.add_metric(name="QueryFailed", unit=MetricUnit.Count, value=1)
        raise InternalServerError(f"Failed to submit query: {e}")


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for query submission."""
    return app.resolve(event, context)
