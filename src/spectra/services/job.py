"""Job management service for DynamoDB persistence."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from aws_lambda_powertools import Logger, Tracer
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from spectra.models.job import Job, JobError, JobResult, JobStatus
from spectra.utils.config import get_settings

logger = Logger()
tracer = Tracer()


class JobNotFoundError(Exception):
    """Raised when a job is not found."""

    pass


class DuplicateJobError(Exception):
    """Raised when a duplicate job is detected via idempotency key."""

    def __init__(self, existing_job_id: str):
        super().__init__(f"Duplicate job detected: {existing_job_id}")
        self.existing_job_id = existing_job_id


class JobService:
    """Service for managing job state in DynamoDB."""

    def __init__(self) -> None:
        """Initialize job service."""
        self.settings = get_settings()
        self.dynamodb = boto3.resource("dynamodb", region_name=self.settings.aws_region)
        self.table = self.dynamodb.Table(self.settings.dynamodb_table_name)

    @staticmethod
    def generate_job_id() -> str:
        """Generate a unique job ID."""
        return f"job-{uuid.uuid4().hex[:12]}"

    @staticmethod
    def hash_sql(sql: str) -> str:
        """Generate a hash of the SQL for deduplication."""
        normalized = " ".join(sql.split()).lower()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _calculate_ttl(self) -> int:
        """Calculate TTL timestamp for DynamoDB."""
        ttl_datetime = datetime.now(UTC) + timedelta(days=self.settings.dynamodb_ttl_days)
        return int(ttl_datetime.timestamp())

    @tracer.capture_method
    def create_job(
        self,
        tenant_id: str,
        sql: str,
        db_user: str,
        db_group: str | None = None,
        output_format: str = "json",
        async_mode: bool = True,
        timeout_seconds: int | None = None,
        idempotency_key: str | None = None,
        batch_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Job:
        """Create a new job record.

        Args:
            tenant_id: Tenant identifier
            sql: SQL query
            db_user: Database user for execution
            db_group: Optional database group
            output_format: Desired output format
            async_mode: Whether to execute asynchronously
            timeout_seconds: Query timeout
            idempotency_key: Optional idempotency key
            batch_id: Optional batch ID for bulk operations
            metadata: Optional custom metadata

        Returns:
            Created Job instance

        Raises:
            DuplicateJobError: If idempotency key matches existing job
        """
        now = datetime.now(UTC)
        job_id = self.generate_job_id()
        sql_hash = self.hash_sql(sql)

        # Check for existing job with same idempotency key
        if idempotency_key:
            existing = self._find_by_idempotency_key(tenant_id, idempotency_key)
            if existing:
                raise DuplicateJobError(existing.job_id)

        job = Job(
            job_id=job_id,
            tenant_id=tenant_id,
            status=JobStatus.QUEUED,
            sql=sql,
            sql_hash=sql_hash,
            db_user=db_user,
            db_group=db_group,
            created_at=now,
            updated_at=now,
            output_format=output_format,
            async_mode=async_mode,
            timeout_seconds=timeout_seconds or self.settings.query_timeout_seconds,
            idempotency_key=idempotency_key,
            batch_id=batch_id,
            metadata=metadata,
            ttl=self._calculate_ttl(),
        )

        # Save to DynamoDB
        try:
            self.table.put_item(
                Item=job.to_dynamo_item(),
                ConditionExpression=Attr("job_id").not_exists(),
            )
            logger.info("Job created", extra={"job_id": job_id, "tenant_id": tenant_id})
            return job

        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise DuplicateJobError(job_id)
            raise

    @tracer.capture_method
    def get_job(self, job_id: str, tenant_id: str | None = None) -> Job:
        """Get a job by ID.

        Args:
            job_id: Job identifier
            tenant_id: Optional tenant ID for validation

        Returns:
            Job instance

        Raises:
            JobNotFoundError: If job not found
        """
        try:
            response = self.table.get_item(Key={"job_id": job_id})
            item = response.get("Item")

            if not item:
                raise JobNotFoundError(f"Job {job_id} not found")

            job = Job.from_dynamo_item(item)

            # Validate tenant access
            if tenant_id and job.tenant_id != tenant_id:
                raise JobNotFoundError(f"Job {job_id} not found")

            return job

        except ClientError as e:
            logger.error("Failed to get job", extra={"job_id": job_id, "error": str(e)})
            raise

    @tracer.capture_method
    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        statement_id: str | None = None,
        result: JobResult | None = None,
        error: JobError | None = None,
    ) -> Job:
        """Update job status and related fields.

        Args:
            job_id: Job identifier
            status: New status
            statement_id: Redshift statement ID
            result: Result info for completed jobs
            error: Error info for failed jobs

        Returns:
            Updated Job instance
        """
        now = datetime.now(UTC)

        update_expr = "SET #status = :status, updated_at = :updated_at"
        expr_names = {"#status": "status"}
        expr_values: dict[str, Any] = {
            ":status": status.value,
            ":updated_at": now.isoformat(),
        }

        # Add statement_id if provided
        if statement_id:
            update_expr += ", statement_id = :statement_id, submitted_at = :submitted_at"
            expr_values[":statement_id"] = statement_id
            expr_values[":submitted_at"] = now.isoformat()

        # Add started_at for RUNNING status
        if status == JobStatus.RUNNING:
            update_expr += ", started_at = :started_at"
            expr_values[":started_at"] = now.isoformat()

        # Add completed_at for terminal states
        if status.is_terminal:
            update_expr += ", completed_at = :completed_at"
            expr_values[":completed_at"] = now.isoformat()

        # Add result for completed jobs
        if result:
            update_expr += ", #result = :result"
            expr_names["#result"] = "result"
            expr_values[":result"] = result.model_dump(mode="json", exclude_none=True)

        # Add error for failed jobs
        if error:
            update_expr += ", #error = :error"
            expr_names["#error"] = "error"
            expr_values[":error"] = error.model_dump(mode="json", exclude_none=True)

        try:
            response = self.table.update_item(
                Key={"job_id": job_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values,
                ReturnValues="ALL_NEW",
            )

            logger.info(
                "Job status updated",
                extra={"job_id": job_id, "status": status.value},
            )

            return Job.from_dynamo_item(response["Attributes"])

        except ClientError as e:
            logger.error(
                "Failed to update job status",
                extra={"job_id": job_id, "error": str(e)},
            )
            raise

    @tracer.capture_method
    def list_jobs(
        self,
        tenant_id: str,
        status: JobStatus | None = None,
        limit: int = 50,
        last_evaluated_key: dict[str, Any] | None = None,
    ) -> tuple[list[Job], dict[str, Any] | None]:
        """List jobs for a tenant.

        Args:
            tenant_id: Tenant identifier
            status: Optional status filter
            limit: Maximum number of results
            last_evaluated_key: Pagination key

        Returns:
            Tuple of (jobs list, last_evaluated_key for pagination)
        """
        try:
            # Build query parameters
            query_params: dict[str, Any] = {
                "IndexName": "tenant-index",
                "KeyConditionExpression": Key("tenant_id").eq(tenant_id),
                "Limit": limit,
                "ScanIndexForward": False,  # Most recent first
            }

            if status:
                query_params["FilterExpression"] = Attr("status").eq(status.value)

            if last_evaluated_key:
                query_params["ExclusiveStartKey"] = last_evaluated_key

            response = self.table.query(**query_params)

            jobs = [Job.from_dynamo_item(item) for item in response.get("Items", [])]
            next_key = response.get("LastEvaluatedKey")

            return jobs, next_key

        except ClientError as e:
            logger.error(
                "Failed to list jobs",
                extra={"tenant_id": tenant_id, "error": str(e)},
            )
            raise

    @tracer.capture_method
    def list_batch_jobs(self, batch_id: str, tenant_id: str) -> list[Job]:
        """List all jobs in a batch.

        Args:
            batch_id: Batch identifier
            tenant_id: Tenant identifier for access control

        Returns:
            List of jobs in the batch
        """
        try:
            response = self.table.query(
                IndexName="batch-index",
                KeyConditionExpression=Key("batch_id").eq(batch_id),
                FilterExpression=Attr("tenant_id").eq(tenant_id),
            )

            return [Job.from_dynamo_item(item) for item in response.get("Items", [])]

        except ClientError as e:
            logger.error(
                "Failed to list batch jobs",
                extra={"batch_id": batch_id, "error": str(e)},
            )
            raise

    def _find_by_idempotency_key(self, tenant_id: str, idempotency_key: str) -> Job | None:
        """Find a job by idempotency key.

        Args:
            tenant_id: Tenant identifier
            idempotency_key: Idempotency key

        Returns:
            Job if found, None otherwise
        """
        try:
            response = self.table.query(
                IndexName="idempotency-index",
                KeyConditionExpression=Key("idempotency_key").eq(idempotency_key),
                FilterExpression=Attr("tenant_id").eq(tenant_id),
                Limit=1,
            )

            items = response.get("Items", [])
            if items:
                return Job.from_dynamo_item(items[0])
            return None

        except ClientError:
            return None

    @tracer.capture_method
    def get_pending_jobs(self, limit: int = 100) -> list[Job]:
        """Get jobs that need status updates (submitted but not complete).

        Args:
            limit: Maximum number of jobs to return

        Returns:
            List of pending jobs
        """
        try:
            response = self.table.scan(
                FilterExpression=Attr("status").is_in(["SUBMITTED", "RUNNING"]),
                Limit=limit,
            )

            return [Job.from_dynamo_item(item) for item in response.get("Items", [])]

        except ClientError as e:
            logger.error("Failed to get pending jobs", extra={"error": str(e)})
            raise

    @tracer.capture_method
    def update_job_submitted(self, job_id: str, statement_id: str) -> Job:
        """Update job with Redshift statement ID.

        Args:
            job_id: Job identifier
            statement_id: Redshift Data API statement ID

        Returns:
            Updated Job instance
        """
        return self.update_job_status(
            job_id=job_id,
            status=JobStatus.SUBMITTED,
            statement_id=statement_id,
        )

    @tracer.capture_method
    def update_job_running(self, job_id: str) -> Job:
        """Mark job as running.

        Args:
            job_id: Job identifier

        Returns:
            Updated Job instance
        """
        return self.update_job_status(
            job_id=job_id,
            status=JobStatus.RUNNING,
        )

    @tracer.capture_method
    def update_job_completed(
        self,
        job_id: str,
        row_count: int = 0,
        size_bytes: int = 0,
    ) -> Job:
        """Mark job as completed with result info.

        Args:
            job_id: Job identifier
            row_count: Number of result rows
            size_bytes: Result size in bytes

        Returns:
            Updated Job instance
        """
        return self.update_job_status(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            result=JobResult(
                row_count=row_count,
                size_bytes=size_bytes,
                location="inline",
            ),
        )

    @tracer.capture_method
    def update_job_failed(
        self,
        job_id: str,
        error_code: str,
        error_message: str,
    ) -> Job:
        """Mark job as failed with error info.

        Args:
            job_id: Job identifier
            error_code: Error code
            error_message: Error message

        Returns:
            Updated Job instance
        """
        return self.update_job_status(
            job_id=job_id,
            status=JobStatus.FAILED,
            error=JobError(
                code=error_code,
                message=error_message,
            ),
        )

    @tracer.capture_method
    def update_job_result_location(
        self,
        job_id: str,
        location: str,
        format: str = "json",
        download_url: str | None = None,
    ) -> Job:
        """Update job with result location in S3.

        Args:
            job_id: Job identifier
            location: S3 URI of the results
            format: Result format (json, csv, parquet)
            download_url: Presigned download URL

        Returns:
            Updated Job instance
        """
        return self.update_job_status(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            result=JobResult(
                row_count=0,  # Already set during export
                location=location,
                format=format,
                download_url=download_url,
            ),
        )
