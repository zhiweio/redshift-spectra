"""Redshift Data API service for query execution.

Optimized with:
- Session Reuse (SessionKeepAliveSeconds) for reduced connection overhead
- CSV format for faster response parsing
- Tenant session association for connection pooling
"""

import csv
import io
import time
from typing import Any, cast

import boto3
from aws_lambda_powertools import Logger, Tracer
from botocore.exceptions import ClientError

from spectra.services.session import SessionService
from spectra.utils.config import get_settings

logger = Logger()
tracer = Tracer()


class RedshiftError(Exception):
    """Base exception for Redshift operations."""

    def __init__(
        self, message: str, code: str | None = None, details: dict[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.details = details


class QueryExecutionError(RedshiftError):
    """Raised when query execution fails."""

    pass


class StatementNotFoundError(RedshiftError):
    """Raised when a statement ID is not found."""

    pass


class QueryTimeoutError(RedshiftError):
    """Raised when a query exceeds the timeout limit."""

    pass


class SessionCreationError(RedshiftError):
    """Raised when session creation fails."""

    pass


class RedshiftService:
    """Service for interacting with Redshift via Data API.

    Features:
    - Session Reuse: Maintains persistent sessions per tenant/user for reduced latency
    - CSV Format: Uses CSV format for faster response parsing
    - Connection Pooling: Associates sessions with tenant users in DynamoDB
    """

    def __init__(self) -> None:
        """Initialize Redshift service."""
        self.settings = get_settings()
        self.client = boto3.client("redshift-data", region_name=self.settings.aws_region)
        self.session_service = SessionService()

    @tracer.capture_method
    def execute_statement(
        self,
        sql: str,
        db_user: str,
        tenant_id: str | None = None,
        statement_name: str | None = None,
        parameters: list[dict[str, Any]] | None = None,
        with_event: bool = False,
        use_session: bool = True,
    ) -> str:
        """Execute a SQL statement asynchronously with session reuse.

        Args:
            sql: SQL statement to execute
            db_user: Database user for RLS context
            tenant_id: Tenant identifier for session association
            statement_name: Optional statement name for tracking
            parameters: Optional query parameters
            with_event: Whether to send CloudWatch event on completion
            use_session: Whether to use session reuse (default True)

        Returns:
            Statement ID for tracking

        Raises:
            QueryExecutionError: If submission fails
        """
        logger.info(
            "Submitting statement to Redshift",
            extra={
                "db_user": db_user,
                "tenant_id": tenant_id,
                "statement_name": statement_name,
                "use_session": use_session,
                "sql_preview": sql[:100] + "..." if len(sql) > 100 else sql,
            },
        )

        try:
            # Build request parameters
            request_params: dict[str, Any] = {
                "Database": self.settings.redshift_database,
                "Sql": sql,
                "WithEvent": with_event,
            }

            # Use either cluster or serverless workgroup
            if self.settings.is_serverless:
                request_params["WorkgroupName"] = self.settings.redshift_workgroup_name
            else:
                request_params["ClusterIdentifier"] = self.settings.redshift_cluster_id
                request_params["SecretArn"] = self.settings.redshift_secret_arn

            # Set the database user for RLS
            request_params["DbUser"] = db_user

            if statement_name:
                request_params["StatementName"] = statement_name

            if parameters:
                request_params["Parameters"] = parameters

            # Session Reuse optimization
            if use_session and tenant_id:
                session_id, _is_new = self.session_service.get_or_create_session_id(
                    tenant_id=tenant_id,
                    db_user=db_user,
                )

                if session_id:
                    # Reuse existing session
                    request_params["SessionId"] = session_id
                    logger.info(
                        "Reusing existing session",
                        extra={"session_id": session_id, "tenant_id": tenant_id},
                    )
                else:
                    # Request new session with keep-alive
                    request_params["SessionKeepAliveSeconds"] = (
                        self.settings.redshift_session_keep_alive_seconds
                    )
                    logger.info(
                        "Creating new session",
                        extra={
                            "keep_alive_seconds": self.settings.redshift_session_keep_alive_seconds,
                            "tenant_id": tenant_id,
                        },
                    )

            response = self.client.execute_statement(**request_params)
            statement_id = response["Id"]

            # If a new session was created, store it in DynamoDB
            if use_session and tenant_id and "SessionId" in response:
                new_session_id = response["SessionId"]
                if new_session_id != request_params.get("SessionId"):
                    self.session_service.create_session(
                        session_id=new_session_id,
                        tenant_id=tenant_id,
                        db_user=db_user,
                    )
                    logger.info(
                        "New session created and stored",
                        extra={"session_id": new_session_id, "tenant_id": tenant_id},
                    )

            logger.info(
                "Statement submitted successfully",
                extra={
                    "statement_id": statement_id,
                    "session_id": response.get("SessionId"),
                },
            )

            return statement_id

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            # Handle session-related errors
            if "Session" in error_message and tenant_id:
                logger.warning(
                    "Session error, invalidating and retrying",
                    extra={"error_code": error_code, "error_message": error_message},
                )
                # Invalidate the bad session and retry without session
                existing_session, _ = self.session_service.get_or_create_session_id(
                    tenant_id, db_user
                )
                if existing_session:
                    self.session_service.invalidate_session(existing_session)
                # Retry without session
                return self.execute_statement(
                    sql=sql,
                    db_user=db_user,
                    tenant_id=tenant_id,
                    statement_name=statement_name,
                    parameters=parameters,
                    with_event=with_event,
                    use_session=False,  # Disable session for retry
                )

            logger.error(
                "Failed to submit statement",
                extra={"error_code": error_code, "error_message": error_message},
            )
            raise QueryExecutionError(
                message=f"Failed to submit query: {error_message}",
                code=error_code,
                details={"original_error": str(e)},
            )

    @tracer.capture_method
    def describe_statement(self, statement_id: str) -> dict[str, Any]:
        """Get the status and metadata of a statement.

        Args:
            statement_id: The statement ID to describe

        Returns:
            Statement description including status

        Raises:
            StatementNotFoundError: If statement ID not found
            RedshiftError: If describe fails
        """
        try:
            response = self.client.describe_statement(Id=statement_id)
            return {
                "id": response["Id"],
                "status": response["Status"],
                "has_result_set": response.get("HasResultSet", False),
                "result_rows": response.get("ResultRows", 0),
                "result_size": response.get("ResultSize", 0),
                "duration": response.get("Duration", 0),
                "error": response.get("Error"),
                "query_string": response.get("QueryString"),
                "created_at": response.get("CreatedAt"),
                "updated_at": response.get("UpdatedAt"),
                "session_id": response.get("SessionId"),
            }

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "ResourceNotFoundException":
                raise StatementNotFoundError(
                    message=f"Statement {statement_id} not found",
                    code=error_code,
                )
            raise RedshiftError(
                message=f"Failed to describe statement: {e}",
                code=error_code,
            )

    @tracer.capture_method
    def wait_for_statement(
        self,
        statement_id: str,
        timeout_seconds: int = 300,
        poll_interval_seconds: float = 0.5,
    ) -> dict[str, Any]:
        """Wait for a statement to complete with polling.

        Implements exponential backoff for efficient polling.

        Args:
            statement_id: The statement ID to wait for
            timeout_seconds: Maximum time to wait (default 300s / 5 minutes)
            poll_interval_seconds: Initial poll interval (will increase with backoff)

        Returns:
            Final statement description

        Raises:
            QueryTimeoutError: If statement doesn't complete within timeout
            QueryExecutionError: If statement fails
            StatementNotFoundError: If statement ID not found
        """
        start_time = time.time()
        current_interval = poll_interval_seconds
        max_interval = 5.0  # Cap backoff at 5 seconds

        logger.info(
            "Waiting for statement completion",
            extra={"statement_id": statement_id, "timeout_seconds": timeout_seconds},
        )

        while True:
            elapsed = time.time() - start_time

            if elapsed >= timeout_seconds:
                logger.warning(
                    "Statement timed out",
                    extra={"statement_id": statement_id, "elapsed_seconds": elapsed},
                )
                raise QueryTimeoutError(
                    message=f"Query exceeded timeout of {timeout_seconds} seconds",
                    code="QUERY_TIMEOUT",
                    details={"statement_id": statement_id, "timeout_seconds": timeout_seconds},
                )

            description = self.describe_statement(statement_id)
            status = description["status"]

            if status == "FINISHED":
                logger.info(
                    "Statement completed",
                    extra={
                        "statement_id": statement_id,
                        "duration_ms": description.get("duration", 0),
                        "result_rows": description.get("result_rows", 0),
                    },
                )
                return description

            if status == "FAILED":
                error_msg = description.get("error", "Unknown error")
                logger.error(
                    "Statement failed",
                    extra={"statement_id": statement_id, "error": error_msg},
                )
                raise QueryExecutionError(
                    message=f"Query failed: {error_msg}",
                    code="QUERY_FAILED",
                    details={"statement_id": statement_id, "error": error_msg},
                )

            if status == "ABORTED":
                logger.warning("Statement was aborted", extra={"statement_id": statement_id})
                raise QueryExecutionError(
                    message="Query was cancelled",
                    code="QUERY_CANCELLED",
                    details={"statement_id": statement_id},
                )

            # Still running, wait and retry with exponential backoff
            time.sleep(current_interval)
            current_interval = min(current_interval * 1.5, max_interval)

    @tracer.capture_method
    def get_statement_result(
        self,
        statement_id: str,
        next_token: str | None = None,
        use_csv_format: bool = True,
    ) -> dict[str, Any]:
        """Get the results of a completed statement.

        Supports both CSV and typed formats:
        - CSV format: Faster parsing, lower memory usage
        - Typed format: Native types preserved

        Args:
            statement_id: The statement ID
            next_token: Pagination token
            use_csv_format: Use CSV format for faster response (default True)

        Returns:
            Result data with records and metadata

        Raises:
            RedshiftError: If getting results fails
        """
        try:
            params: dict[str, Any] = {"Id": statement_id}
            if next_token:
                params["NextToken"] = next_token

            # Request CSV format for faster parsing
            if use_csv_format:
                response = self.client.get_statement_result_v2(
                    **params,
                    Format="CSV",
                )
                return self._parse_csv_result(cast(dict[str, Any], response))
            else:
                response = self.client.get_statement_result(**params)
                return self._parse_typed_result(cast(dict[str, Any], response))

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")

            # Fallback to typed format if CSV not supported
            if error_code == "ValidationException" and use_csv_format:
                logger.warning(
                    "CSV format not supported, falling back to typed format",
                    extra={"statement_id": statement_id},
                )
                return self.get_statement_result(
                    statement_id=statement_id,
                    next_token=next_token,
                    use_csv_format=False,
                )

            raise RedshiftError(
                message=f"Failed to get statement result: {e}",
                code=error_code,
            )

    def _parse_csv_result(self, response: dict[str, Any]) -> dict[str, Any]:
        """Parse CSV format result from get_statement_result_v2.

        Args:
            response: Raw response from Redshift Data API

        Returns:
            Parsed result with columns and records
        """
        # Extract column metadata
        columns = [
            {
                "name": col.get("name", f"col_{i}"),
                "type": col.get("typeName", "unknown"),
                "label": col.get("label", col.get("name", f"col_{i}")),
            }
            for i, col in enumerate(response.get("ColumnMetadata", []))
        ]
        column_names = [c["name"] for c in columns]

        # Parse CSV formatted records
        records = []
        formatted_records = response.get("FormattedRecords", "")

        if formatted_records:
            # Use CSV reader to handle proper escaping
            csv_reader = csv.reader(io.StringIO(formatted_records))

            for row in csv_reader:
                if len(row) == len(column_names):
                    record = {}
                    for i, value in enumerate(row):
                        col_name = column_names[i]
                        # Convert empty strings to None for nullable fields
                        record[col_name] = value if value != "" else None
                    records.append(record)

        return {
            "columns": columns,
            "records": records,
            "total_rows": response.get("TotalNumRows", len(records)),
            "next_token": response.get("NextToken"),
            "format": "CSV",
        }

    def _parse_typed_result(self, response: dict[str, Any]) -> dict[str, Any]:
        """Parse typed format result from get_statement_result.

        Args:
            response: Raw response from Redshift Data API

        Returns:
            Parsed result with columns and records
        """
        # Extract column metadata
        columns = [
            {
                "name": col.get("name", f"col_{i}"),
                "type": col.get("typeName", "unknown"),
                "label": col.get("label", col.get("name", f"col_{i}")),
            }
            for i, col in enumerate(response.get("ColumnMetadata", []))
        ]
        column_names = [c["name"] for c in columns]

        # Convert records to list of dicts
        records = []
        for row in response.get("Records", []):
            record = {}
            for i, cell in enumerate(row):
                col_name = column_names[i] if i < len(column_names) else f"col_{i}"
                # Extract value from the typed field
                if "stringValue" in cell:
                    record[col_name] = cell["stringValue"]
                elif "longValue" in cell:
                    record[col_name] = cell["longValue"]
                elif "doubleValue" in cell:
                    record[col_name] = cell["doubleValue"]
                elif "booleanValue" in cell:
                    record[col_name] = cell["booleanValue"]
                elif "blobValue" in cell:
                    record[col_name] = cell["blobValue"]
                elif cell.get("isNull"):
                    record[col_name] = None
                else:
                    record[col_name] = None
            records.append(record)

        return {
            "columns": columns,
            "records": records,
            "total_rows": response.get("TotalNumRows", len(records)),
            "next_token": response.get("NextToken"),
            "format": "TYPED",
        }

    @tracer.capture_method
    def get_all_statement_results(
        self,
        statement_id: str,
        use_csv_format: bool = True,
        max_rows: int | None = None,
    ) -> dict[str, Any]:
        """Get all results of a completed statement with automatic pagination.

        Handles pagination automatically by following NextToken until all
        results are retrieved or max_rows is reached.

        Args:
            statement_id: The statement ID
            use_csv_format: Use CSV format for faster response (default True)
            max_rows: Optional maximum number of rows to retrieve (for inline results)

        Returns:
            Complete result data with all records merged

        Raises:
            RedshiftError: If getting results fails
        """
        all_records: list[dict[str, Any]] = []
        columns: list[dict[str, Any]] = []
        next_token: str | None = None
        total_rows = 0
        result_format = "CSV" if use_csv_format else "TYPED"
        page_count = 0

        logger.info(
            "Fetching all statement results",
            extra={"statement_id": statement_id, "max_rows": max_rows},
        )

        while True:
            page_count += 1
            result = self.get_statement_result(
                statement_id=statement_id,
                next_token=next_token,
                use_csv_format=use_csv_format,
            )

            # Store columns from first page
            if not columns:
                columns = result.get("columns", [])

            # Append records
            page_records = result.get("records", [])
            all_records.extend(page_records)

            # Update total rows from API response
            if result.get("total_rows"):
                total_rows = result["total_rows"]

            # Update format from response
            if result.get("format"):
                result_format = result["format"]

            logger.debug(
                "Fetched result page",
                extra={
                    "page": page_count,
                    "page_records": len(page_records),
                    "total_fetched": len(all_records),
                },
            )

            # Check if we've reached max_rows limit
            if max_rows and len(all_records) >= max_rows:
                logger.info(
                    "Reached max_rows limit, stopping pagination",
                    extra={"max_rows": max_rows, "fetched": len(all_records)},
                )
                all_records = all_records[:max_rows]
                break

            # Check for more pages
            next_token = result.get("next_token")
            if not next_token:
                break

        logger.info(
            "Completed fetching all results",
            extra={
                "statement_id": statement_id,
                "pages_fetched": page_count,
                "total_records": len(all_records),
                "total_rows_reported": total_rows,
            },
        )

        return {
            "columns": columns,
            "records": all_records,
            "total_rows": total_rows or len(all_records),
            "format": result_format,
            "pages_fetched": page_count,
        }

    @tracer.capture_method
    def cancel_statement(self, statement_id: str) -> bool:
        """Cancel a running statement.

        Args:
            statement_id: The statement ID to cancel

        Returns:
            True if cancellation was successful

        Raises:
            RedshiftError: If cancellation fails
        """
        try:
            response = self.client.cancel_statement(Id=statement_id)
            logger.info(
                "Statement cancelled",
                extra={"statement_id": statement_id, "status": response.get("Status")},
            )
            return response.get("Status", False)

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            raise RedshiftError(
                message=f"Failed to cancel statement: {e}",
                code=error_code,
            )

    @tracer.capture_method
    def execute_unload(
        self,
        sql: str,
        s3_path: str,
        db_user: str,
        iam_role: str,
        tenant_id: str | None = None,
        file_format: str = "PARQUET",
        partition_by: list[str] | None = None,
    ) -> str:
        """Execute an UNLOAD statement to export data to S3.

        Args:
            sql: SELECT query to export
            s3_path: S3 destination path
            db_user: Database user
            iam_role: IAM role ARN for S3 access
            tenant_id: Tenant identifier for session reuse
            file_format: Output format (PARQUET, CSV, JSON)
            partition_by: Optional partition columns

        Returns:
            Statement ID for tracking

        Raises:
            QueryExecutionError: If UNLOAD fails
        """
        # Build UNLOAD SQL
        unload_options = [
            f"FORMAT {file_format}",
            "PARALLEL ON",
            "ALLOWOVERWRITE",
        ]

        if partition_by:
            partition_cols = ", ".join(partition_by)
            unload_options.append(f"PARTITION BY ({partition_cols})")

        options_str = "\n".join(unload_options)

        unload_sql = f"""
        UNLOAD ('{sql.replace("'", "''")}')
        TO '{s3_path}'
        IAM_ROLE '{iam_role}'
        {options_str};
        """

        return self.execute_statement(
            sql=unload_sql,
            db_user=db_user,
            tenant_id=tenant_id,
            statement_name="unload_export",
        )

    @tracer.capture_method
    def invalidate_tenant_sessions(self, tenant_id: str, db_user: str | None = None) -> int:
        """Invalidate all sessions for a tenant.

        Args:
            tenant_id: Tenant identifier
            db_user: Optional specific db_user to invalidate

        Returns:
            Number of sessions invalidated
        """
        return self.session_service.cleanup_expired_sessions(tenant_id)

    def map_status(self, redshift_status: str) -> str:
        """Map Redshift Data API status to our job status.

        Args:
            redshift_status: Status from Redshift Data API

        Returns:
            Mapped job status
        """
        status_mapping = {
            "SUBMITTED": "SUBMITTED",
            "PICKED": "RUNNING",
            "STARTED": "RUNNING",
            "FINISHED": "COMPLETED",
            "FAILED": "FAILED",
            "ABORTED": "CANCELLED",
        }
        return status_mapping.get(redshift_status, "RUNNING")
