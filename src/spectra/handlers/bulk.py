"""Bulk API Lambda handler following Salesforce Bulk v2 design.

This module implements a Bulk API for large-scale data import/export operations,
inspired by Salesforce Bulk API v2.

Workflow:
1. Create Job: POST /v1/bulk/jobs
2. Upload Data (for import): PUT /v1/bulk/jobs/{job_id}/batches
3. Close Job: PATCH /v1/bulk/jobs/{job_id} (state: UploadComplete)
4. Monitor: GET /v1/bulk/jobs/{job_id}
5. Get Results: GET /v1/bulk/jobs/{job_id}/results
"""

import contextlib
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
from pydantic import ValidationError

from spectra.middleware.tenant import TenantContext, extract_tenant_context
from spectra.models.bulk import (
    BulkJobCreateRequest,
    BulkJobState,
    BulkJobUpdateRequest,
    BulkOperation,
)
from spectra.services.bulk import BulkJobNotFoundError, BulkJobService
from spectra.utils.response import api_response

logger = Logger()
tracer = Tracer()
metrics = Metrics()
app = APIGatewayRestResolver()


# =============================================================================
# Job Management Endpoints
# =============================================================================


@app.post("/v1/bulk/jobs")
@tracer.capture_method
def create_bulk_job() -> Response:
    """Create a new bulk job.

    For QUERY (export) operations:
        - Provide `query` with the SQL SELECT statement
        - Job processes immediately, results available via GET /results

    For INSERT/UPDATE/UPSERT/DELETE (import) operations:
        - Provide `object` (table name)
        - Upload data via PUT /batches endpoint
        - Close job to start processing

    Returns:
        Created bulk job info with content URL for upload
    """
    try:
        tenant_ctx: TenantContext = extract_tenant_context(app.current_event)
    except ValueError as e:
        raise UnauthorizedError(str(e))

    logger.append_keys(tenant_id=tenant_ctx.tenant_id)

    # Parse request
    try:
        body = app.current_event.json_body
        request = BulkJobCreateRequest.model_validate(body)
    except ValidationError as e:
        raise BadRequestError(f"Invalid request: {e.errors()}")
    except Exception as e:
        raise BadRequestError(f"Invalid JSON body: {e!s}")

    # Validate operation-specific requirements
    if request.operation == BulkOperation.QUERY:
        if not request.query:
            raise BadRequestError("Query is required for export operations")
    elif not request.object:
        raise BadRequestError("Object (table name) is required for import operations")

    bulk_service = BulkJobService()

    # Create bulk job
    job = bulk_service.create_job(
        tenant_id=tenant_ctx.tenant_id,
        db_user=tenant_ctx.db_user,
        operation=request.operation,
        query=request.query,
        object_name=request.object,
        external_id_field=request.external_id_field,
        column_mappings=request.column_mappings,
        content_type=request.content_type,
        compression=request.compression,
        line_ending=request.line_ending,
        column_delimiter=request.column_delimiter,
    )

    metrics.add_metric(name="BulkJobCreated", unit=MetricUnit.Count, value=1)
    metrics.add_metadata(key="operation", value=request.operation.value)

    logger.info(
        "Bulk job created",
        extra={
            "job_id": job.job_id,
            "operation": request.operation.value,
            "content_type": request.content_type.value,
        },
    )

    return api_response(201, job.model_dump(mode="json"))


@app.get("/v1/bulk/jobs/<job_id>")
@tracer.capture_method
def get_bulk_job(job_id: str) -> Response:
    """Get bulk job information.

    Args:
        job_id: Bulk job identifier

    Returns:
        Bulk job info with current state
    """
    try:
        tenant_ctx: TenantContext = extract_tenant_context(app.current_event)
    except ValueError as e:
        raise UnauthorizedError(str(e))

    logger.append_keys(tenant_id=tenant_ctx.tenant_id, job_id=job_id)

    bulk_service = BulkJobService()

    try:
        job = bulk_service.get_job(job_id, tenant_id=tenant_ctx.tenant_id)
        return api_response(200, job.model_dump(mode="json"))
    except BulkJobNotFoundError:
        raise NotFoundError(f"Bulk job not found: {job_id}")


@app.patch("/v1/bulk/jobs/<job_id>")
@tracer.capture_method
def update_bulk_job(job_id: str) -> Response:
    """Update bulk job state.

    Valid state transitions:
        - Open -> UploadComplete: Finalize upload and start processing
        - Open -> Aborted: Cancel the job
        - UploadComplete -> Aborted: Cancel processing

    Args:
        job_id: Bulk job identifier

    Returns:
        Updated bulk job info
    """
    try:
        tenant_ctx: TenantContext = extract_tenant_context(app.current_event)
    except ValueError as e:
        raise UnauthorizedError(str(e))

    logger.append_keys(tenant_id=tenant_ctx.tenant_id, job_id=job_id)

    # Parse request
    try:
        body = app.current_event.json_body
        request = BulkJobUpdateRequest.model_validate(body)
    except ValidationError as e:
        raise BadRequestError(f"Invalid request: {e.errors()}")

    bulk_service = BulkJobService()

    try:
        if request.state == "UploadComplete":
            job = bulk_service.close_job(job_id, tenant_id=tenant_ctx.tenant_id)
            metrics.add_metric(name="BulkJobClosed", unit=MetricUnit.Count, value=1)
        else:  # Aborted
            job = bulk_service.abort_job(job_id, tenant_id=tenant_ctx.tenant_id)
            metrics.add_metric(name="BulkJobAborted", unit=MetricUnit.Count, value=1)

        logger.info("Bulk job updated", extra={"new_state": request.state})

        return api_response(200, job.model_dump(mode="json"))

    except BulkJobNotFoundError:
        raise NotFoundError(f"Bulk job not found: {job_id}")


@app.delete("/v1/bulk/jobs/<job_id>")
@tracer.capture_method
def delete_bulk_job(job_id: str) -> Response:
    """Delete a bulk job.

    Only jobs in terminal states can be deleted.

    Args:
        job_id: Bulk job identifier

    Returns:
        Empty response on success
    """
    try:
        tenant_ctx: TenantContext = extract_tenant_context(app.current_event)
    except ValueError as e:
        raise UnauthorizedError(str(e))

    logger.append_keys(tenant_id=tenant_ctx.tenant_id, job_id=job_id)

    bulk_service = BulkJobService()

    try:
        bulk_service.delete_job(job_id, tenant_id=tenant_ctx.tenant_id)
        metrics.add_metric(name="BulkJobDeleted", unit=MetricUnit.Count, value=1)

        return api_response(204, None)

    except BulkJobNotFoundError:
        raise NotFoundError(f"Bulk job not found: {job_id}")


@app.get("/v1/bulk/jobs")
@tracer.capture_method
def list_bulk_jobs() -> Response:
    """List bulk jobs for the current tenant.

    Query Parameters:
        - operation: Filter by operation type
        - state: Filter by job state
        - limit: Maximum number of jobs to return (default: 50, max: 100)
        - cursor: Pagination cursor

    Returns:
        List of bulk jobs
    """
    try:
        tenant_ctx: TenantContext = extract_tenant_context(app.current_event)
    except ValueError as e:
        raise UnauthorizedError(str(e))

    logger.append_keys(tenant_id=tenant_ctx.tenant_id)

    # Parse query parameters
    params = app.current_event.query_string_parameters or {}
    limit = min(int(params.get("limit", "50")), 100)
    operation_str = params.get("operation")
    state_str = params.get("state")
    next_token = params.get("cursor")  # API uses cursor, service uses next_token

    # Convert to enums if provided
    operation: BulkOperation | None = None
    if operation_str:
        with contextlib.suppress(ValueError):
            operation = BulkOperation(operation_str)

    state: BulkJobState | None = None
    if state_str:
        with contextlib.suppress(ValueError):
            state = BulkJobState(state_str)

    bulk_service = BulkJobService()

    jobs, next_cursor = bulk_service.list_jobs(
        tenant_id=tenant_ctx.tenant_id,
        operation=operation,
        state=state,
        limit=limit,
        next_token=next_token,
    )

    return api_response(
        200,
        {
            "jobs": [job.model_dump(mode="json") for job in jobs],
            "next_cursor": next_cursor,
            "has_more": next_cursor is not None,
        },
    )


# =============================================================================
# Data Upload/Download Endpoints
# =============================================================================


@app.put("/v1/bulk/jobs/<job_id>/batches")
@tracer.capture_method
def upload_batch_data(job_id: str) -> Response:
    """Upload data for a bulk import job.

    The request body should contain the data in the format specified
    when creating the job (CSV, JSON, or Parquet).

    For large files, use the presigned URL returned in the job creation response.

    Args:
        job_id: Bulk job identifier

    Returns:
        Batch info with record count
    """
    try:
        tenant_ctx: TenantContext = extract_tenant_context(app.current_event)
    except ValueError as e:
        raise UnauthorizedError(str(e))

    logger.append_keys(tenant_id=tenant_ctx.tenant_id, job_id=job_id)

    bulk_service = BulkJobService()

    try:
        # Get job to validate state
        job = bulk_service.get_job(job_id, tenant_id=tenant_ctx.tenant_id)

        if job.state != BulkJobState.OPEN:
            raise BadRequestError(f"Job is not open for upload. Current state: {job.state.value}")

        if job.operation == BulkOperation.QUERY:
            raise BadRequestError("Cannot upload data for query (export) jobs")

        # Get raw body
        body = app.current_event.body
        if not body:
            raise BadRequestError("Request body is required")

        # Process the uploaded data
        batch_info = bulk_service.add_batch(
            job_id=job_id,
            tenant_id=tenant_ctx.tenant_id,
            data=body,
            content_type=job.content_type,
        )

        metrics.add_metric(name="BulkBatchUploaded", unit=MetricUnit.Count, value=1)

        return api_response(201, batch_info)

    except BulkJobNotFoundError:
        raise NotFoundError(f"Bulk job not found: {job_id}")


@app.get("/v1/bulk/jobs/<job_id>/results")
@tracer.capture_method
def get_bulk_job_results(job_id: str) -> Response:
    """Get results for a completed bulk job.

    For QUERY (export) jobs:
        - Returns presigned URL to download exported data

    For import jobs:
        - Returns processing statistics and failed records

    Args:
        job_id: Bulk job identifier

    Returns:
        Job results with download URLs or statistics
    """
    try:
        tenant_ctx: TenantContext = extract_tenant_context(app.current_event)
    except ValueError as e:
        raise UnauthorizedError(str(e))

    logger.append_keys(tenant_id=tenant_ctx.tenant_id, job_id=job_id)

    bulk_service = BulkJobService()

    try:
        job = bulk_service.get_job(job_id, tenant_id=tenant_ctx.tenant_id)

        if job.state not in {BulkJobState.JOB_COMPLETE, BulkJobState.FAILED}:
            raise BadRequestError(f"Job results not available. Current state: {job.state.value}")

        result = bulk_service.get_job_results(job_id, tenant_id=tenant_ctx.tenant_id)

        return api_response(200, result)

    except BulkJobNotFoundError:
        raise NotFoundError(f"Bulk job not found: {job_id}")


# =============================================================================
# Lambda Handler
# =============================================================================


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler for bulk operations."""
    return app.resolve(event, context)
