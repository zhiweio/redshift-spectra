"""S3 export service for large result sets."""

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import boto3
from aws_lambda_powertools import Logger, Tracer
from botocore.exceptions import ClientError

from spectra.utils.config import get_settings

logger = Logger()
tracer = Tracer()


class ExportError(Exception):
    """Base exception for export operations."""

    pass


class ExportService:
    """Service for exporting large datasets to S3."""

    def __init__(self) -> None:
        """Initialize export service."""
        self.settings = get_settings()
        self.s3_client = boto3.client("s3", region_name=self.settings.aws_region)

    @tracer.capture_method
    def write_json_results(
        self,
        job_id: str,
        tenant_id: str,
        data: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Write JSON results to S3.

        Args:
            job_id: Job identifier
            tenant_id: Tenant identifier
            data: Result data to write
            metadata: Optional metadata

        Returns:
            S3 URI of the written file

        Raises:
            ExportError: If write fails
        """
        key = self._build_key(tenant_id, job_id, "json")

        try:
            body = json.dumps(
                {
                    "metadata": metadata or {},
                    "data": data,
                    "row_count": len(data),
                    "exported_at": datetime.now(UTC).isoformat(),
                },
                default=str,
            )

            self.s3_client.put_object(
                Bucket=self.settings.s3_bucket_name,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType="application/json",
                Metadata={
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "row_count": str(len(data)),
                },
            )

            s3_uri = f"s3://{self.settings.s3_bucket_name}/{key}"
            logger.info(
                "Exported JSON results to S3",
                extra={"s3_uri": s3_uri, "row_count": len(data)},
            )

            return s3_uri

        except ClientError as e:
            logger.error("Failed to export JSON to S3", extra={"error": str(e)})
            raise ExportError(f"Failed to export results: {e}")

    @tracer.capture_method
    def write_csv_results(
        self,
        job_id: str,
        tenant_id: str,
        columns: list[str],
        data: list[dict[str, Any]],
    ) -> str:
        """Write CSV results to S3.

        Args:
            job_id: Job identifier
            tenant_id: Tenant identifier
            columns: Column names
            data: Result data to write

        Returns:
            S3 URI of the written file

        Raises:
            ExportError: If write fails
        """
        key = self._build_key(tenant_id, job_id, "csv")

        try:
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)

            body = output.getvalue()

            self.s3_client.put_object(
                Bucket=self.settings.s3_bucket_name,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType="text/csv",
                Metadata={
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "row_count": str(len(data)),
                },
            )

            s3_uri = f"s3://{self.settings.s3_bucket_name}/{key}"
            logger.info(
                "Exported CSV results to S3",
                extra={"s3_uri": s3_uri, "row_count": len(data)},
            )

            return s3_uri

        except ClientError as e:
            logger.error("Failed to export CSV to S3", extra={"error": str(e)})
            raise ExportError(f"Failed to export results: {e}")

    @tracer.capture_method
    def generate_presigned_url(
        self,
        s3_uri: str,
        expiry_seconds: int | None = None,
    ) -> tuple[str, datetime]:
        """Generate a presigned URL for downloading results.

        Args:
            s3_uri: S3 URI of the file
            expiry_seconds: URL expiration in seconds

        Returns:
            Tuple of (presigned URL, expiration datetime)

        Raises:
            ExportError: If URL generation fails
        """
        expiry = expiry_seconds or self.settings.presigned_url_expiry

        # Parse S3 URI
        parsed = urlparse(s3_uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expiry,
            )

            expires_at = datetime.now(UTC) + timedelta(seconds=expiry)

            logger.info(
                "Generated presigned URL",
                extra={"s3_uri": s3_uri, "expires_at": expires_at.isoformat()},
            )

            return url, expires_at

        except ClientError as e:
            logger.error("Failed to generate presigned URL", extra={"error": str(e)})
            raise ExportError(f"Failed to generate download URL: {e}")

    @tracer.capture_method
    def get_object_info(self, s3_uri: str) -> dict[str, Any]:
        """Get object metadata from S3.

        Args:
            s3_uri: S3 URI of the file

        Returns:
            Object metadata including size and content type

        Raises:
            ExportError: If object not found or access denied
        """
        parsed = urlparse(s3_uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")

        try:
            response = self.s3_client.head_object(Bucket=bucket, Key=key)

            return {
                "size_bytes": response.get("ContentLength", 0),
                "content_type": response.get("ContentType", "application/octet-stream"),
                "last_modified": response.get("LastModified"),
                "metadata": response.get("Metadata", {}),
            }

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "404":
                raise ExportError(f"Object not found: {s3_uri}")
            raise ExportError(f"Failed to get object info: {e}")

    @tracer.capture_method
    def delete_export(self, s3_uri: str) -> bool:
        """Delete an exported file from S3.

        Args:
            s3_uri: S3 URI of the file to delete

        Returns:
            True if deletion was successful
        """
        parsed = urlparse(s3_uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")

        try:
            self.s3_client.delete_object(Bucket=bucket, Key=key)
            logger.info("Deleted export", extra={"s3_uri": s3_uri})
            return True

        except ClientError as e:
            logger.error("Failed to delete export", extra={"s3_uri": s3_uri, "error": str(e)})
            return False

    @tracer.capture_method
    def build_unload_path(self, tenant_id: str, job_id: str) -> str:
        """Build S3 path for UNLOAD operations.

        Args:
            tenant_id: Tenant identifier
            job_id: Job identifier

        Returns:
            S3 path for UNLOAD destination
        """
        date_prefix = datetime.now(UTC).strftime("%Y/%m/%d")
        return (
            f"s3://{self.settings.s3_bucket_name}/"
            f"{self.settings.s3_prefix}"
            f"{tenant_id}/{date_prefix}/{job_id}/"
        )

    def _build_key(self, tenant_id: str, job_id: str, extension: str) -> str:
        """Build S3 key for a result file.

        Args:
            tenant_id: Tenant identifier
            job_id: Job identifier
            extension: File extension

        Returns:
            S3 key
        """
        date_prefix = datetime.now(UTC).strftime("%Y/%m/%d")
        return f"{self.settings.s3_prefix}{tenant_id}/{date_prefix}/{job_id}/results.{extension}"

    @tracer.capture_method
    def list_exports(
        self,
        tenant_id: str,
        prefix: str | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """List exports for a tenant.

        Args:
            tenant_id: Tenant identifier
            prefix: Optional additional prefix filter
            max_results: Maximum number of results

        Returns:
            List of export objects
        """
        full_prefix = f"{self.settings.s3_prefix}{tenant_id}/"
        if prefix:
            full_prefix += prefix

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.settings.s3_bucket_name,
                Prefix=full_prefix,
                MaxKeys=max_results,
            )

            exports = []
            for obj in response.get("Contents", []):
                exports.append(
                    {
                        "key": obj["Key"],
                        "size_bytes": obj["Size"],
                        "last_modified": obj["LastModified"],
                        "s3_uri": f"s3://{self.settings.s3_bucket_name}/{obj['Key']}",
                    }
                )

            return exports

        except ClientError as e:
            logger.error("Failed to list exports", extra={"tenant_id": tenant_id, "error": str(e)})
            return []
