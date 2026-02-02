"""Result retrieval Lambda handler."""

from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.exceptions import (
    BadRequestError,
    NotFoundError,
    UnauthorizedError,
)
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from spectra.middleware.tenant import TenantContext, extract_tenant_context
from spectra.models.job import JobStatus
from spectra.services.export import ExportService
from spectra.services.job import JobNotFoundError, JobService
from spectra.services.redshift import RedshiftService
from spectra.utils.config import get_settings
from spectra.utils.response import api_response

logger = Logger()
tracer = Tracer()
metrics = Metrics()
app = APIGatewayRestResolver()
settings = get_settings()


@app.get("/v1/jobs/<job_id>/results")
@tracer.capture_method
def get_job_results(job_id: str) -> Response:
    """Get the results of a completed job.

    For small result sets, returns inline JSON.
    For large result sets, returns a presigned S3 URL.

    Args:
        job_id: Job identifier

    Returns:
        Result data or download URL
    """
    # Extract tenant context
    try:
        tenant_ctx: TenantContext = extract_tenant_context(app.current_event)
    except ValueError as e:
        raise UnauthorizedError(str(e))

    logger.append_keys(tenant_id=tenant_ctx.tenant_id, job_id=job_id)

    job_service = JobService()
    redshift_service = RedshiftService()
    export_service = ExportService()

    try:
        # Get job from DynamoDB
        job = job_service.get_job(job_id, tenant_id=tenant_ctx.tenant_id)

        # Get status value
        job_status_str = job.status if isinstance(job.status, str) else job.status.value
        job_status = JobStatus(job.status) if isinstance(job.status, str) else job.status

        # Check if job is completed
        if job_status == JobStatus.FAILED:
            return api_response(
                200,
                {
                    "job_id": job.job_id,
                    "status": "FAILED",
                    "error": job.error.model_dump() if job.error else {"message": "Unknown error"},
                },
            )

        if job_status != JobStatus.COMPLETED:
            raise BadRequestError(f"Job is not completed. Current status: {job_status_str}")

        # If results already exported to S3, return presigned URL
        if job.result and job.result.location and job.result.location != "inline":
            download_url, expires_at = export_service.generate_presigned_url(job.result.location)

            return api_response(
                200,
                {
                    "job_id": job.job_id,
                    "status": "COMPLETED",
                    "download_url": download_url,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                    "format": job.result.format,
                    "size_bytes": job.result.size_bytes,
                    "row_count": job.result.row_count,
                },
            )

        # For inline results or no cached result, fetch from Redshift
        # Fetch results from Redshift with automatic pagination
        if not job.statement_id:
            raise BadRequestError("No statement ID found for this job")

        # Use get_all_statement_results to handle pagination automatically
        # For inline results, we limit to threshold to avoid memory issues
        # For S3 export, we fetch all results
        result = redshift_service.get_all_statement_results(
            statement_id=job.statement_id,
            max_rows=settings.result_size_threshold
            * 2,  # Fetch enough to determine if S3 export needed
        )

        row_count = result.get("total_rows", 0)
        columns = result.get("columns", [])
        data = result.get("records", [])

        # Check if results should be offloaded to S3
        if row_count > settings.result_size_threshold:
            logger.info(
                "Offloading large result set to S3",
                extra={"row_count": row_count, "threshold": settings.result_size_threshold},
            )

            # Export to S3 based on requested format
            if job.output_format == "csv":
                s3_uri = export_service.write_csv_results(
                    job_id=job.job_id,
                    tenant_id=tenant_ctx.tenant_id,
                    columns=columns,
                    data=data,
                )
            elif job.output_format == "parquet":
                s3_uri = export_service.write_parquet_results(
                    job_id=job.job_id,
                    tenant_id=tenant_ctx.tenant_id,
                    columns=columns,
                    data=data,
                )
            else:
                s3_uri = export_service.write_json_results(
                    job_id=job.job_id,
                    tenant_id=tenant_ctx.tenant_id,
                    data=data,
                    metadata={"columns": columns},
                )

            # Generate presigned URL
            download_url, _ = export_service.generate_presigned_url(s3_uri)

            # Update job with result location
            job_service.update_job_result_location(
                job_id=job.job_id,
                location=s3_uri,
                format=job.output_format,
                download_url=download_url,
            )

            metrics.add_metric(name="ResultExportedToS3", unit=MetricUnit.Count, value=1)

            return api_response(
                200,
                {
                    "job_id": job.job_id,
                    "status": "COMPLETED",
                    "download_url": download_url,
                    "format": job.output_format,
                    "row_count": row_count,
                },
            )

        # Return inline results
        metrics.add_metric(name="ResultReturnedInline", unit=MetricUnit.Count, value=1)

        return api_response(
            200,
            {
                "job_id": job.job_id,
                "status": "COMPLETED",
                "data": data,
                "metadata": {
                    "columns": columns,
                    "row_count": row_count,
                },
            },
        )

    except JobNotFoundError:
        raise NotFoundError(f"Job not found: {job_id}")


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for result retrieval."""
    return app.resolve(event, context)
