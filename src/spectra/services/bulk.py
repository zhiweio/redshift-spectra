"""Bulk Job Service for large-scale data import/export operations.

This service implements Salesforce Bulk v2 compatible workflow:
1. Create Job -> Open state
2. Upload Data (for import) -> Still Open
3. Close Job -> UploadComplete, triggers processing
4. Monitor Progress -> InProgress
5. Get Results -> JobComplete/Failed

Supports multiple formats (CSV, JSON, Parquet) and compression types.
"""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from aws_lambda_powertools import Logger, Tracer
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from spectra.models.bulk import (
    BulkJobInfo,
    BulkJobState,
    BulkOperation,
    CompressionType,
    DataFormat,
    LineEnding,
)
from spectra.utils.config import get_settings

logger = Logger()
tracer = Tracer()


class BulkJobNotFoundError(Exception):
    """Raised when a bulk job is not found."""

    pass


class BulkJobStateError(Exception):
    """Raised when job state transition is invalid."""

    def __init__(self, job_id: str, current_state: str, requested_state: str):
        super().__init__(
            f"Invalid state transition for job {job_id}: {current_state} -> {requested_state}"
        )
        self.job_id = job_id
        self.current_state = current_state
        self.requested_state = requested_state


class BulkJobService:
    """Service for managing bulk import/export jobs.

    Implements Salesforce Bulk v2 compatible state machine with support
    for CSV, JSON, and Parquet formats with various compression options.
    """

    def __init__(self) -> None:
        """Initialize bulk job service."""
        self.settings = get_settings()
        self.dynamodb = boto3.resource("dynamodb", region_name=self.settings.aws_region)
        self.table = self.dynamodb.Table(self.settings.dynamodb_bulk_table_name)
        self.s3_client = boto3.client("s3", region_name=self.settings.aws_region)

    @staticmethod
    def generate_job_id() -> str:
        """Generate a unique bulk job ID."""
        return f"bulk-{uuid.uuid4().hex[:16]}"

    def _calculate_ttl(self, days: int | None = None) -> int:
        """Calculate TTL timestamp for DynamoDB."""
        ttl_days = days or self.settings.bulk_job_ttl_days
        ttl_datetime = datetime.now(UTC) + timedelta(days=ttl_days)
        return int(ttl_datetime.timestamp())

    def _get_s3_prefix(self, tenant_id: str, job_id: str) -> str:
        """Get S3 prefix for job data."""
        return f"bulk/{tenant_id}/{job_id}"

    def _get_content_url(
        self,
        tenant_id: str,
        job_id: str,
        operation: BulkOperation,
        content_type: DataFormat,
        compression: CompressionType,
    ) -> str:
        """Generate S3 content URL for upload/download.

        Args:
            tenant_id: Tenant identifier
            job_id: Job identifier
            operation: Bulk operation type
            content_type: Data format
            compression: Compression type

        Returns:
            S3 URI for the data file
        """
        prefix = self._get_s3_prefix(tenant_id, job_id)
        extension = self._get_file_extension(content_type, compression)

        if operation == BulkOperation.QUERY:
            return f"s3://{self.settings.s3_bucket_name}/{prefix}/results/data{extension}"
        else:
            return f"s3://{self.settings.s3_bucket_name}/{prefix}/input/data{extension}"

    @staticmethod
    def _get_file_extension(
        content_type: DataFormat,
        compression: CompressionType,
    ) -> str:
        """Get file extension based on format and compression.

        Args:
            content_type: Data format
            compression: Compression type

        Returns:
            File extension string
        """
        format_extensions = {
            DataFormat.CSV: ".csv",
            DataFormat.JSON: ".json",
            DataFormat.PARQUET: ".parquet",
        }

        compression_extensions = {
            CompressionType.NONE: "",
            CompressionType.GZIP: ".gz",
            CompressionType.LZOP: ".lzo",
            CompressionType.BZIP2: ".bz2",
            CompressionType.ZSTD: ".zst",
        }

        base_ext = format_extensions.get(content_type, ".csv")
        comp_ext = compression_extensions.get(compression, "")

        # Parquet has built-in compression, don't add extension
        if content_type == DataFormat.PARQUET:
            return base_ext

        return f"{base_ext}{comp_ext}"

    @tracer.capture_method
    def create_job(
        self,
        tenant_id: str,
        db_user: str,
        operation: BulkOperation,
        query: str | None = None,
        object_name: str | None = None,
        external_id_field: str | None = None,
        column_mappings: list[dict] | None = None,
        content_type: DataFormat = DataFormat.CSV,
        compression: CompressionType = CompressionType.GZIP,
        line_ending: LineEnding = LineEnding.LF,
        column_delimiter: str = ",",
        assignment_rule_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BulkJobInfo:
        """Create a new bulk job.

        For QUERY (export) operations, job starts processing immediately.
        For import operations, job enters Open state awaiting data upload.

        Args:
            tenant_id: Tenant identifier
            db_user: Database user for RLS
            operation: Type of bulk operation
            query: SQL query for export operations
            object_name: Target table for import operations
            external_id_field: Key column for upsert/update
            column_mappings: Column mappings for import
            content_type: Data format
            compression: Compression type
            line_ending: Line ending for CSV
            column_delimiter: Column delimiter for CSV
            assignment_rule_id: Custom assignment rule
            metadata: Custom metadata

        Returns:
            Created BulkJobInfo

        Raises:
            ValueError: If required fields are missing
        """
        now = datetime.now(UTC)
        job_id = self.generate_job_id()

        # Validate operation requirements
        if operation == BulkOperation.QUERY and not query:
            raise ValueError("Query is required for export operations")
        if operation != BulkOperation.QUERY and not object_name:
            raise ValueError("Object (table name) is required for import operations")
        if operation in (BulkOperation.UPSERT, BulkOperation.UPDATE) and not external_id_field:
            raise ValueError("external_id_field is required for upsert/update operations")

        # Determine initial state
        # For query operations, start processing immediately
        # For import operations, wait for data upload
        initial_state = (
            BulkJobState.IN_PROGRESS if operation == BulkOperation.QUERY else BulkJobState.OPEN
        )

        content_url = self._get_content_url(tenant_id, job_id, operation, content_type, compression)

        job_item = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "operation": operation.value,
            "state": initial_state.value,
            "db_user": db_user,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "system_modstamp": now.isoformat(),
            "content_type": content_type.value,
            "compression": compression.value,
            "line_ending": line_ending.value,
            "column_delimiter": column_delimiter,
            "content_url": content_url,
            "api_version": "v1",
            "concurrency_mode": "Parallel",
            "number_records_processed": 0,
            "number_records_failed": 0,
            "retries": 0,
            "total_processing_time": 0,
            "ttl": self._calculate_ttl(),
        }

        # Add optional fields
        if query:
            job_item["query"] = query
        if object_name:
            job_item["object"] = object_name
        if external_id_field:
            job_item["external_id_field"] = external_id_field
        if column_mappings:
            job_item["column_mappings"] = column_mappings
        if assignment_rule_id:
            job_item["assignment_rule_id"] = assignment_rule_id
        if metadata:
            job_item["metadata"] = metadata

        # Save to DynamoDB
        try:
            self.table.put_item(
                Item=job_item,
                ConditionExpression=Attr("job_id").not_exists(),
            )
            logger.info(
                "Bulk job created",
                extra={
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "operation": operation.value,
                    "state": initial_state.value,
                },
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(
                "Failed to create bulk job",
                extra={"error_code": error_code, "error": str(e)},
            )
            raise

        return self._item_to_job_info(job_item)

    @tracer.capture_method
    def get_job(self, job_id: str, tenant_id: str | None = None) -> BulkJobInfo:
        """Get a bulk job by ID.

        Args:
            job_id: Job identifier
            tenant_id: Optional tenant ID for validation

        Returns:
            BulkJobInfo

        Raises:
            BulkJobNotFoundError: If job not found or tenant mismatch
        """
        try:
            response = self.table.get_item(Key={"job_id": job_id})
            item = response.get("Item")

            if not item:
                raise BulkJobNotFoundError(f"Bulk job not found: {job_id}")

            if tenant_id and item.get("tenant_id") != tenant_id:
                raise BulkJobNotFoundError(f"Bulk job not found: {job_id}")

            return self._item_to_job_info(item)

        except ClientError as e:
            logger.error("Failed to get bulk job", extra={"job_id": job_id, "error": str(e)})
            raise

    @tracer.capture_method
    def list_jobs(
        self,
        tenant_id: str,
        state: BulkJobState | None = None,
        operation: BulkOperation | None = None,
        limit: int = 100,
        next_token: str | None = None,
    ) -> tuple[list[BulkJobInfo], str | None]:
        """List bulk jobs for a tenant.

        Args:
            tenant_id: Tenant identifier
            state: Optional state filter
            operation: Optional operation filter
            limit: Maximum number of results
            next_token: Pagination token

        Returns:
            Tuple of (jobs list, next_token)
        """
        try:
            query_params = {
                "IndexName": "tenant-state-index",
                "KeyConditionExpression": Key("tenant_id").eq(tenant_id),
                "Limit": min(limit, 1000),
                "ScanIndexForward": False,  # Most recent first
            }

            # Add state filter if provided
            if state:
                query_params["KeyConditionExpression"] &= Key("state").eq(state.value)

            # Add operation filter if provided
            if operation:
                query_params["FilterExpression"] = Attr("operation").eq(operation.value)

            if next_token:
                decoded = json.loads(base64.b64decode(next_token).decode())
                query_params["ExclusiveStartKey"] = decoded

            response = self.table.query(**query_params)
            items = response.get("Items", [])
            jobs = [self._item_to_job_info(item) for item in items]

            # Generate next token if there are more results
            new_next_token = None
            if "LastEvaluatedKey" in response:
                new_next_token = base64.b64encode(
                    json.dumps(response["LastEvaluatedKey"]).encode()
                ).decode()

            return jobs, new_next_token

        except ClientError as e:
            logger.error(
                "Failed to list bulk jobs",
                extra={"tenant_id": tenant_id, "error": str(e)},
            )
            raise

    @tracer.capture_method
    def update_job_state(
        self,
        job_id: str,
        tenant_id: str,
        new_state: BulkJobState,
    ) -> BulkJobInfo:
        """Update bulk job state.

        Valid transitions:
        - Open -> UploadComplete (client finished upload)
        - UploadComplete -> InProgress (processing starts)
        - InProgress -> JobComplete (success)
        - InProgress -> Failed (error)
        - Any non-terminal -> Aborted (user cancellation)

        Args:
            job_id: Job identifier
            tenant_id: Tenant identifier
            new_state: New state

        Returns:
            Updated BulkJobInfo

        Raises:
            BulkJobNotFoundError: If job not found
            BulkJobStateError: If transition is invalid
        """
        current_job = self.get_job(job_id, tenant_id)

        # Validate state transition
        if not self._is_valid_transition(BulkJobState(current_job.state), new_state):
            raise BulkJobStateError(
                job_id=job_id,
                current_state=current_job.state.value,
                requested_state=new_state.value,
            )

        now = datetime.now(UTC)

        try:
            response = self.table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET #state = :state, updated_at = :updated_at, system_modstamp = :modstamp",
                ExpressionAttributeNames={"#state": "state"},
                ExpressionAttributeValues={
                    ":state": new_state.value,
                    ":updated_at": now.isoformat(),
                    ":modstamp": now.isoformat(),
                    ":expected_tenant": tenant_id,
                },
                ConditionExpression=Attr("tenant_id").eq(tenant_id),
                ReturnValues="ALL_NEW",
            )

            logger.info(
                "Bulk job state updated",
                extra={
                    "job_id": job_id,
                    "old_state": current_job.state.value,
                    "new_state": new_state.value,
                },
            )

            return self._item_to_job_info(response["Attributes"])

        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise BulkJobNotFoundError(f"Bulk job not found: {job_id}")
            raise

    @tracer.capture_method
    def update_job_progress(
        self,
        job_id: str,
        records_processed: int = 0,
        records_failed: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Update job progress counters.

        Args:
            job_id: Job identifier
            records_processed: Number of records processed
            records_failed: Number of records failed
            error_message: Error message if any
        """
        now = datetime.now(UTC)

        update_expr = """
            SET number_records_processed = number_records_processed + :processed,
                number_records_failed = number_records_failed + :failed,
                updated_at = :updated_at
        """

        expr_values = {
            ":processed": records_processed,
            ":failed": records_failed,
            ":updated_at": now.isoformat(),
        }

        if error_message:
            update_expr += ", error_message = :error"
            expr_values[":error"] = error_message

        try:
            self.table.update_item(
                Key={"job_id": job_id},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
            )
        except ClientError as e:
            logger.error(
                "Failed to update job progress",
                extra={"job_id": job_id, "error": str(e)},
            )

    @tracer.capture_method
    def get_upload_url(
        self,
        job_id: str,
        tenant_id: str,
        content_type: DataFormat,
        compression: CompressionType,
        expiration_seconds: int = 3600,
    ) -> str:
        """Generate presigned URL for data upload.

        Args:
            job_id: Job identifier
            tenant_id: Tenant identifier
            content_type: Data format
            compression: Compression type
            expiration_seconds: URL expiration time

        Returns:
            Presigned URL for PUT operation
        """
        job = self.get_job(job_id, tenant_id)

        if job.state != BulkJobState.OPEN:
            raise BulkJobStateError(
                job_id=job_id,
                current_state=job.state.value,
                requested_state="UPLOAD",
            )

        prefix = self._get_s3_prefix(tenant_id, job_id)
        extension = self._get_file_extension(content_type, compression)
        key = f"{prefix}/input/data{extension}"

        # Determine Content-Type header
        content_type_header = self._get_content_type_header(content_type, compression)

        url = self.s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.settings.s3_bucket_name,
                "Key": key,
                "ContentType": content_type_header,
            },
            ExpiresIn=expiration_seconds,
        )

        return url

    @tracer.capture_method
    def get_download_url(
        self,
        job_id: str,
        tenant_id: str,
        file_type: str = "results",
        expiration_seconds: int = 3600,
    ) -> str:
        """Generate presigned URL for result download.

        Args:
            job_id: Job identifier
            tenant_id: Tenant identifier
            file_type: 'results' or 'failed'
            expiration_seconds: URL expiration time

        Returns:
            Presigned URL for GET operation
        """
        job = self.get_job(job_id, tenant_id)

        if job.state not in (BulkJobState.JOB_COMPLETE, BulkJobState.FAILED):
            raise BulkJobStateError(
                job_id=job_id,
                current_state=job.state.value,
                requested_state="DOWNLOAD",
            )

        prefix = self._get_s3_prefix(tenant_id, job_id)
        extension = self._get_file_extension(
            DataFormat(job.content_type),
            CompressionType(job.compression)
            if hasattr(job, "compression")
            else CompressionType.GZIP,
        )
        key = f"{prefix}/{file_type}/data{extension}"

        url = self.s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.settings.s3_bucket_name,
                "Key": key,
            },
            ExpiresIn=expiration_seconds,
        )

        return url

    @tracer.capture_method
    def list_result_files(
        self,
        job_id: str,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        """List result files for a job.

        Args:
            job_id: Job identifier
            tenant_id: Tenant identifier

        Returns:
            List of file information dictionaries
        """
        self.get_job(job_id, tenant_id)  # Validate job exists
        prefix = self._get_s3_prefix(tenant_id, job_id)

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.settings.s3_bucket_name,
                Prefix=f"{prefix}/results/",
            )

            files = []
            for obj in response.get("Contents", []):
                files.append(
                    {
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat(),
                        "download_url": self.s3_client.generate_presigned_url(
                            "get_object",
                            Params={
                                "Bucket": self.settings.s3_bucket_name,
                                "Key": obj["Key"],
                            },
                            ExpiresIn=3600,
                        ),
                    }
                )

            return files

        except ClientError as e:
            logger.error(
                "Failed to list result files",
                extra={"job_id": job_id, "error": str(e)},
            )
            return []

    @staticmethod
    def _is_valid_transition(current: BulkJobState, new: BulkJobState) -> bool:
        """Check if state transition is valid.

        Args:
            current: Current state
            new: Requested new state

        Returns:
            True if transition is valid
        """
        # Cannot transition from terminal states
        if current.is_terminal:
            return False

        # Aborted is allowed from any non-terminal state
        if new == BulkJobState.ABORTED:
            return True

        # Valid transitions
        valid_transitions = {
            BulkJobState.OPEN: {BulkJobState.UPLOAD_COMPLETE},
            BulkJobState.UPLOAD_COMPLETE: {BulkJobState.IN_PROGRESS},
            BulkJobState.IN_PROGRESS: {BulkJobState.JOB_COMPLETE, BulkJobState.FAILED},
        }

        return new in valid_transitions.get(current, set())

    @staticmethod
    def _get_content_type_header(
        content_type: DataFormat,
        compression: CompressionType,
    ) -> str:
        """Get HTTP Content-Type header for file upload.

        Args:
            content_type: Data format
            compression: Compression type

        Returns:
            Content-Type header value
        """
        base_types = {
            DataFormat.CSV: "text/csv",
            DataFormat.JSON: "application/json",
            DataFormat.PARQUET: "application/octet-stream",
        }

        base = base_types.get(content_type, "application/octet-stream")

        # For compressed files, use octet-stream
        if compression != CompressionType.NONE:
            return "application/octet-stream"

        return base

    def _item_to_job_info(self, item: dict[str, Any]) -> BulkJobInfo:
        """Convert DynamoDB item to BulkJobInfo.

        Args:
            item: DynamoDB item

        Returns:
            BulkJobInfo instance
        """
        return BulkJobInfo(
            id=item["job_id"],
            operation=BulkOperation(item["operation"]),
            state=BulkJobState(item["state"]),
            object=item.get("object"),
            created_by_id=item.get("tenant_id", ""),
            created_date=datetime.fromisoformat(item["created_at"]),
            system_modstamp=datetime.fromisoformat(item.get("system_modstamp", item["updated_at"])),
            content_type=DataFormat(item.get("content_type", "CSV")),
            line_ending=LineEnding(item.get("line_ending", "LF")),
            column_delimiter=item.get("column_delimiter", ","),
            number_records_processed=item.get("number_records_processed", 0),
            number_records_failed=item.get("number_records_failed", 0),
            retries=item.get("retries", 0),
            total_processing_time=item.get("total_processing_time", 0),
            api_version=item.get("api_version", "v1"),
            concurrency_mode=item.get("concurrency_mode", "Parallel"),
            content_url=item.get("content_url"),
            error_message=item.get("error_message"),
            job_type="V2Query" if item["operation"] == "query" else "V2Ingest",
        )
