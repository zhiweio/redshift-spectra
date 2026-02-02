"""Background worker Lambda handler.

This handler processes async bulk jobs triggered by DynamoDB Streams,
SQS, or EventBridge events. It handles data export/import operations
and updates job status accordingly.
"""

import json
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from spectra.models.bulk import BulkJobState, BulkOperation
from spectra.models.job import JobStatus
from spectra.services.bulk import BulkJobService
from spectra.services.export import ExportService
from spectra.services.job import JobService
from spectra.services.redshift import RedshiftService

logger = Logger()
tracer = Tracer()
metrics = Metrics()


@tracer.capture_method
def process_query_job(job_id: str, tenant_id: str) -> dict[str, Any]:
    """Process a query export job.

    Args:
        job_id: Job identifier
        tenant_id: Tenant identifier

    Returns:
        Processing result
    """
    job_service = JobService()
    redshift_service = RedshiftService()
    export_service = ExportService()

    try:
        # Get job details
        job = job_service.get_job(job_id, tenant_id=tenant_id)

        if job.status not in {JobStatus.QUEUED, JobStatus.SUBMITTED, JobStatus.RUNNING}:
            logger.info(f"Job {job_id} is not in processable state: {job.status}")
            return {"status": "skipped", "reason": f"Job status is {job.status}"}

        # Update to running
        job_service.update_job_running(job_id)

        # Check statement status if we have a statement ID
        if job.statement_id:
            statement_info = redshift_service.describe_statement(job.statement_id)
            status = statement_info.get("status", "")

            if status == "FINISHED":
                # Get results and export to S3
                results = redshift_service.get_statement_result(job.statement_id)

                # Export to S3
                export_result = export_service.export_results(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    results=results,
                    format=job.result.format if job.result else "json",
                )

                # Update job as completed
                job_service.update_job_completed(
                    job_id=job_id,
                    row_count=len(results.get("records", [])),
                    size_bytes=export_result.get("size_bytes", 0),
                    location=export_result.get("location"),
                )

                return {"status": "completed", "location": export_result.get("location")}

            elif status == "FAILED":
                error_message = statement_info.get("error", "Unknown error")
                job_service.update_job_failed(
                    job_id=job_id,
                    error_code="REDSHIFT_ERROR",
                    error_message=error_message,
                )
                return {"status": "failed", "error": error_message}

            else:
                # Still processing
                return {"status": "processing", "redshift_status": status}

        return {"status": "pending", "reason": "No statement ID"}

    except Exception as e:
        logger.exception(f"Error processing job {job_id}")
        job_service.update_job_failed(
            job_id=job_id,
            error_code="WORKER_ERROR",
            error_message=str(e),
        )
        return {"status": "failed", "error": str(e)}


@tracer.capture_method
def process_bulk_job(job_id: str, tenant_id: str) -> dict[str, Any]:
    """Process a bulk job.

    Args:
        job_id: Bulk job identifier
        tenant_id: Tenant identifier

    Returns:
        Processing result
    """
    bulk_service = BulkJobService()

    try:
        # Get bulk job details with tenant validation
        job = bulk_service.get_job(job_id, tenant_id=tenant_id)

        # Check if job state is processable
        current_state = job.state
        if current_state not in [
            BulkJobState.UPLOAD_COMPLETE.value,
            BulkJobState.IN_PROGRESS.value,
            "UploadComplete",
            "InProgress",
        ]:
            logger.info(f"Bulk job {job_id} is not in processable state: {current_state}")
            return {"status": "skipped", "reason": f"Job state is {current_state}"}

        # Update to in progress
        bulk_service.update_job_state(job_id, tenant_id, BulkJobState.IN_PROGRESS)

        if job.operation in {BulkOperation.QUERY, "query"}:
            # For query operations, the actual processing is handled by
            # the Redshift Data API. We just track the state here.
            # The statement execution is initiated when the job is created.

            # Mark as complete for now (real implementation would poll Redshift)
            bulk_service.update_job_state(job_id, tenant_id, BulkJobState.JOB_COMPLETE)

            metrics.add_metric(
                name="BulkJobCompleted",
                unit=MetricUnit.Count,
                value=1,
            )

            return {"status": "completed", "job_id": job_id}

        # Handle other operations (INSERT, UPDATE, DELETE)
        # These would be processed differently based on uploaded data
        return {"status": "pending", "operation": str(job.operation)}

    except Exception as e:
        logger.exception(f"Error processing bulk job {job_id}")
        try:
            bulk_service.update_job_state(job_id, tenant_id, BulkJobState.FAILED)
        except Exception:
            logger.exception("Failed to update job state to FAILED")
        return {"status": "failed", "error": str(e)}


@tracer.capture_method
def process_sqs_record(record: dict[str, Any]) -> dict[str, Any]:
    """Process a single SQS record.

    Args:
        record: SQS record

    Returns:
        Processing result
    """
    body = json.loads(record.get("body", "{}"))

    job_type = body.get("job_type", "query")
    job_id = body.get("job_id")
    tenant_id = body.get("tenant_id")

    if not job_id or not tenant_id:
        logger.warning("Missing job_id or tenant_id in SQS message")
        return {"status": "error", "reason": "Missing required fields"}

    logger.append_keys(job_id=job_id, tenant_id=tenant_id, job_type=job_type)

    if job_type == "bulk":
        return process_bulk_job(job_id, tenant_id)
    else:
        return process_query_job(job_id, tenant_id)


@tracer.capture_method
def process_dynamodb_record(record: dict[str, Any]) -> dict[str, Any]:
    """Process a DynamoDB Streams record.

    Args:
        record: DynamoDB Streams record

    Returns:
        Processing result
    """
    event_name = record.get("eventName", "")

    # Only process INSERT and MODIFY events
    if event_name not in ["INSERT", "MODIFY"]:
        return {"status": "skipped", "reason": f"Event {event_name} not processed"}

    new_image = record.get("dynamodb", {}).get("NewImage", {})

    # Extract job ID and tenant ID from DynamoDB image
    job_id = new_image.get("job_id", {}).get("S")
    tenant_id = new_image.get("tenant_id", {}).get("S")
    status = new_image.get("status", {}).get("S")

    if not job_id or not tenant_id:
        return {"status": "skipped", "reason": "Missing job or tenant ID"}

    logger.append_keys(job_id=job_id, tenant_id=tenant_id, status=status)

    # Only process PENDING jobs
    if status != "PENDING":
        return {"status": "skipped", "reason": f"Job status is {status}"}

    return process_query_job(job_id, tenant_id)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:  # noqa: ARG001
    """Worker Lambda handler.

    Processes events from SQS, DynamoDB Streams, or direct invocation.

    Args:
        event: Lambda event
        context: Lambda context

    Returns:
        Processing results
    """
    results = []

    # Handle SQS events
    if "Records" in event:
        for record in event["Records"]:
            event_source = record.get("eventSource", "")

            if event_source == "aws:sqs":
                result = process_sqs_record(record)
            elif event_source == "aws:dynamodb":
                result = process_dynamodb_record(record)
            else:
                result = {"status": "skipped", "reason": f"Unknown event source: {event_source}"}

            results.append(result)

    # Handle direct invocation
    elif "job_id" in event:
        job_id = event["job_id"]
        tenant_id = event.get("tenant_id", "default")
        job_type = event.get("job_type", "query")

        logger.append_keys(job_id=job_id, tenant_id=tenant_id, job_type=job_type)

        if job_type == "bulk":
            result = process_bulk_job(job_id, tenant_id)
        else:
            result = process_query_job(job_id, tenant_id)

        results.append(result)

    else:
        logger.warning("Unknown event format", extra={"event_keys": list(event.keys())})
        return {"status": "error", "reason": "Unknown event format"}

    # Summarize results
    completed = sum(1 for r in results if r.get("status") == "completed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    skipped = sum(1 for r in results if r.get("status") == "skipped")

    metrics.add_metric(name="JobsProcessed", unit=MetricUnit.Count, value=len(results))
    metrics.add_metric(name="JobsCompleted", unit=MetricUnit.Count, value=completed)
    metrics.add_metric(name="JobsFailed", unit=MetricUnit.Count, value=failed)

    return {
        "status": "ok",
        "processed": len(results),
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
        "results": results,
    }
