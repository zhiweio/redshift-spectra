"""Redshift Data API service for query execution.

Optimized with:
- Session Reuse (SessionKeepAliveSeconds) for reduced connection overhead
- CSV format for faster response parsing
- Tenant session association for connection pooling
"""

import csv
import io
from typing import Any

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
                return self._parse_csv_result(response)
            else:
                response = self.client.get_statement_result(**params)
                return self._parse_typed_result(response)

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
    def invalidate_tenant_sessions(self, tenant_id: str, db_user: str | None = None) -> int:  # noqa: ARG002
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
