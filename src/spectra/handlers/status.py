"""Job status Lambda handler."""

from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.exceptions import (
    NotFoundError,
    UnauthorizedError,
)
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext

from spectra.middleware.tenant import TenantContext, extract_tenant_context
from spectra.models.job import JobStatus
from spectra.services.job import JobNotFoundError, JobService
from spectra.services.redshift import RedshiftService, StatementNotFoundError
from spectra.utils.response import api_response

logger = Logger()
tracer = Tracer()
metrics = Metrics()
app = APIGatewayRestResolver()


@app.get("/v1/jobs/<job_id>")
@tracer.capture_method
def get_job_status(job_id: str) -> Response:
    """Get the status of a job.

    Args:
        job_id: Job identifier

    Returns:
        Job status response
    """
    # Extract tenant context
    try:
        tenant_ctx: TenantContext = extract_tenant_context(app.current_event)
    except ValueError as e:
        raise UnauthorizedError(str(e))

    logger.append_keys(tenant_id=tenant_ctx.tenant_id, job_id=job_id)

    job_service = JobService()
    redshift_service = RedshiftService()

    try:
        # Get job from DynamoDB
        job = job_service.get_job(job_id, tenant_id=tenant_ctx.tenant_id)

        # Convert status to enum if it's a string (due to use_enum_values config)
        job_status = JobStatus(job.status) if isinstance(job.status, str) else job.status

        # If job is still running, check Redshift for updates
        if not job_status.is_terminal and job.statement_id:
            try:
                statement_info = redshift_service.describe_statement(job.statement_id)
                new_status = _map_redshift_status(statement_info["status"])

                if new_status != job_status:
                    # Update job status
                    if new_status == JobStatus.COMPLETED:
                        job = job_service.update_job_completed(
                            job_id=job.job_id,
                            row_count=statement_info.get("result_rows", 0),
                            size_bytes=statement_info.get("result_size", 0),
                        )
                    elif new_status == JobStatus.FAILED:
                        job = job_service.update_job_failed(
                            job_id=job.job_id,
                            error_code="REDSHIFT_ERROR",
                            error_message=statement_info.get("error", "Unknown error"),
                        )
                    elif new_status == JobStatus.RUNNING:
                        job = job_service.update_job_running(job.job_id)

            except StatementNotFoundError:
                logger.warning(
                    "Statement not found in Redshift", extra={"statement_id": job.statement_id}
                )

        # Get status value
        status_str = job.status if isinstance(job.status, str) else job.status.value
        logger.info("Job status retrieved", extra={"status": status_str})

        return api_response(
            200,
            {
                "job_id": job.job_id,
                "status": status_str,
                "submitted_at": job.created_at.isoformat(),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "duration_ms": job.duration_ms,
                "row_count": job.result.row_count if job.result else None,
                "result_location": job.result.location if job.result else None,
                "error": job.error.model_dump() if job.error else None,
            },
        )

    except JobNotFoundError:
        raise NotFoundError(f"Job not found: {job_id}")


@app.get("/v1/jobs")
@tracer.capture_method
def list_jobs() -> Response:
    """List jobs for the current tenant.

    Returns:
        List of jobs
    """
    # Extract tenant context
    try:
        tenant_ctx: TenantContext = extract_tenant_context(app.current_event)
    except ValueError as e:
        raise UnauthorizedError(str(e))

    logger.append_keys(tenant_id=tenant_ctx.tenant_id)

    # Parse query parameters
    params = app.current_event.query_string_parameters or {}
    limit = min(int(params.get("limit", "50")), 100)
    status_filter = params.get("status")
    cursor = params.get("cursor")

    job_service = JobService()

    # List jobs
    jobs, next_cursor = job_service.list_jobs(
        tenant_id=tenant_ctx.tenant_id,
        limit=limit,
        status=status_filter,
        cursor=cursor,
    )

    return api_response(
        200,
        {
            "jobs": [
                {
                    "job_id": job.job_id,
                    "status": job.status if isinstance(job.status, str) else job.status.value,
                    "submitted_at": job.created_at.isoformat(),
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                }
                for job in jobs
            ],
            "next_cursor": next_cursor,
            "has_more": next_cursor is not None,
        },
    )


def _map_redshift_status(redshift_status: str) -> JobStatus:
    """Map Redshift Data API status to JobStatus.

    Args:
        redshift_status: Status from Redshift Data API

    Returns:
        Mapped JobStatus
    """
    status_map = {
        "SUBMITTED": JobStatus.SUBMITTED,
        "PICKED": JobStatus.RUNNING,
        "STARTED": JobStatus.RUNNING,
        "FINISHED": JobStatus.COMPLETED,
        "FAILED": JobStatus.FAILED,
        "ABORTED": JobStatus.CANCELLED,
    }
    return status_map.get(redshift_status, JobStatus.RUNNING)


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for job status."""
    return app.resolve(event, context)
