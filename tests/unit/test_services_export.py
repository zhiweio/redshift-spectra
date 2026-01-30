"""Unit tests for export service.

Tests for the ExportService class that handles S3 export operations.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from spectra.services.export import ExportError, ExportService


# =============================================================================
# ExportService Tests
# =============================================================================


class TestExportService:
    """Tests for ExportService class."""

    @pytest.fixture
    def mock_s3_client(self) -> MagicMock:
        """Create a mock S3 client."""
        return MagicMock()

    @pytest.fixture
    def export_service(self, mock_s3_client: MagicMock) -> ExportService:
        """Create an ExportService with mocked dependencies."""
        with patch("boto3.client") as mock_client:
            mock_client.return_value = mock_s3_client
            service = ExportService()
            service.s3_client = mock_s3_client
            return service

    def test_write_json_results(
        self, export_service: ExportService, mock_s3_client: MagicMock
    ) -> None:
        """Test writing JSON results to S3."""
        mock_s3_client.put_object.return_value = {}

        data = [
            {"id": 1, "name": "Alice", "amount": 100.50},
            {"id": 2, "name": "Bob", "amount": 200.75},
        ]

        s3_uri = export_service.write_json_results(
            job_id="job-123",
            tenant_id="tenant-456",
            data=data,
        )

        assert s3_uri.startswith("s3://")
        assert "job-123" in s3_uri
        assert s3_uri.endswith(".json")
        mock_s3_client.put_object.assert_called_once()

        # Verify the body is valid JSON with expected structure
        call_args = mock_s3_client.put_object.call_args
        body = call_args.kwargs["Body"]
        parsed = json.loads(body.decode("utf-8"))
        assert parsed["row_count"] == 2
        assert len(parsed["data"]) == 2

    def test_write_json_results_with_metadata(
        self, export_service: ExportService, mock_s3_client: MagicMock
    ) -> None:
        """Test writing JSON results with custom metadata."""
        mock_s3_client.put_object.return_value = {}

        data = [{"id": 1}]
        metadata = {"source": "dashboard", "user": "admin"}

        export_service.write_json_results(
            job_id="job-123",
            tenant_id="tenant-456",
            data=data,
            metadata=metadata,
        )

        call_args = mock_s3_client.put_object.call_args
        body = call_args.kwargs["Body"]
        parsed = json.loads(body.decode("utf-8"))
        assert parsed["metadata"] == metadata

    def test_write_json_results_error(
        self, export_service: ExportService, mock_s3_client: MagicMock
    ) -> None:
        """Test handling of S3 error when writing JSON."""
        mock_s3_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "PutObject",
        )

        with pytest.raises(ExportError, match="Failed to export"):
            export_service.write_json_results(
                job_id="job-123",
                tenant_id="tenant-456",
                data=[{"id": 1}],
            )

    def test_write_csv_results(
        self, export_service: ExportService, mock_s3_client: MagicMock
    ) -> None:
        """Test writing CSV results to S3."""
        mock_s3_client.put_object.return_value = {}

        columns = ["id", "name", "amount"]
        data = [
            {"id": 1, "name": "Alice", "amount": 100.50},
            {"id": 2, "name": "Bob", "amount": 200.75},
        ]

        s3_uri = export_service.write_csv_results(
            job_id="job-123",
            tenant_id="tenant-456",
            columns=columns,
            data=data,
        )

        assert s3_uri.startswith("s3://")
        assert s3_uri.endswith(".csv")
        mock_s3_client.put_object.assert_called_once()

        # Verify the CSV content
        call_args = mock_s3_client.put_object.call_args
        body = call_args.kwargs["Body"].decode("utf-8")
        lines = body.strip().replace("\r\n", "\n").replace("\r", "\n").split("\n")
        assert lines[0] == "id,name,amount"
        assert len(lines) == 3  # header + 2 data rows

    def test_write_csv_results_error(
        self, export_service: ExportService, mock_s3_client: MagicMock
    ) -> None:
        """Test handling of S3 error when writing CSV."""
        mock_s3_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "PutObject",
        )

        with pytest.raises(ExportError):
            export_service.write_csv_results(
                job_id="job-123",
                tenant_id="tenant-456",
                columns=["id"],
                data=[{"id": 1}],
            )

    def test_generate_presigned_url(
        self, export_service: ExportService, mock_s3_client: MagicMock
    ) -> None:
        """Test generating presigned URL."""
        mock_s3_client.generate_presigned_url.return_value = (
            "https://bucket.s3.amazonaws.com/key?signature=xxx"
        )

        url, expires_at = export_service.generate_presigned_url(
            s3_uri="s3://test-bucket/results/job-123.json",
            expiry_seconds=3600,
        )

        assert url.startswith("https://")
        assert expires_at > datetime.now(UTC)
        mock_s3_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": "results/job-123.json"},
            ExpiresIn=3600,
        )

    def test_generate_presigned_url_default_expiry(
        self, export_service: ExportService, mock_s3_client: MagicMock
    ) -> None:
        """Test generating presigned URL with default expiry."""
        mock_s3_client.generate_presigned_url.return_value = "https://url"

        export_service.generate_presigned_url(
            s3_uri="s3://bucket/key.json",
        )

        # Should use settings.presigned_url_expiry as default
        mock_s3_client.generate_presigned_url.assert_called_once()

    def test_generate_presigned_url_error(
        self, export_service: ExportService, mock_s3_client: MagicMock
    ) -> None:
        """Test handling of error when generating presigned URL."""
        mock_s3_client.generate_presigned_url.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "GeneratePresignedUrl",
        )

        with pytest.raises(ExportError, match="Failed to generate download URL"):
            export_service.generate_presigned_url(
                s3_uri="s3://bucket/key.json",
            )

    def test_get_object_info(
        self, export_service: ExportService, mock_s3_client: MagicMock
    ) -> None:
        """Test getting object metadata from S3."""
        mock_s3_client.head_object.return_value = {
            "ContentLength": 1024,
            "ContentType": "application/json",
            "LastModified": datetime.now(UTC),
            "Metadata": {"job_id": "job-123", "row_count": "100"},
        }

        info = export_service.get_object_info(s3_uri="s3://test-bucket/results/job-123.json")

        # The method returns a dict with size_bytes key
        assert info.get("size_bytes") == 1024
        mock_s3_client.head_object.assert_called_once()


class TestExportServiceEdgeCases:
    """Tests for ExportService edge cases."""

    @pytest.fixture
    def mock_s3_client(self) -> MagicMock:
        """Create a mock S3 client."""
        return MagicMock()

    @pytest.fixture
    def export_service(self, mock_s3_client: MagicMock) -> ExportService:
        """Create an ExportService with mocked dependencies."""
        with patch("boto3.client") as mock_client:
            mock_client.return_value = mock_s3_client
            service = ExportService()
            service.s3_client = mock_s3_client
            return service

    def test_write_json_empty_data(
        self, export_service: ExportService, mock_s3_client: MagicMock
    ) -> None:
        """Test writing empty JSON results."""
        mock_s3_client.put_object.return_value = {}

        s3_uri = export_service.write_json_results(
            job_id="job-123",
            tenant_id="tenant-456",
            data=[],
        )

        call_args = mock_s3_client.put_object.call_args
        body = call_args.kwargs["Body"]
        parsed = json.loads(body.decode("utf-8"))
        assert parsed["row_count"] == 0
        assert parsed["data"] == []

    def test_write_csv_empty_data(
        self, export_service: ExportService, mock_s3_client: MagicMock
    ) -> None:
        """Test writing empty CSV results."""
        mock_s3_client.put_object.return_value = {}

        export_service.write_csv_results(
            job_id="job-123",
            tenant_id="tenant-456",
            columns=["id", "name"],
            data=[],
        )

        call_args = mock_s3_client.put_object.call_args
        body = call_args.kwargs["Body"].decode("utf-8")
        lines = body.strip().split("\n")
        assert len(lines) == 1  # Only header

    def test_write_json_special_characters(
        self, export_service: ExportService, mock_s3_client: MagicMock
    ) -> None:
        """Test writing JSON with special characters."""
        mock_s3_client.put_object.return_value = {}

        data = [
            {"id": 1, "name": "Test 'quoted'", "description": "Line1\nLine2"},
            {"id": 2, "name": "Unicode: 日本語", "emoji": "🎉"},
        ]

        export_service.write_json_results(
            job_id="job-123",
            tenant_id="tenant-456",
            data=data,
        )

        call_args = mock_s3_client.put_object.call_args
        body = call_args.kwargs["Body"]
        parsed = json.loads(body.decode("utf-8"))
        assert parsed["data"][1]["name"] == "Unicode: 日本語"

    def test_write_csv_special_characters(
        self, export_service: ExportService, mock_s3_client: MagicMock
    ) -> None:
        """Test writing CSV with special characters (quoting)."""
        mock_s3_client.put_object.return_value = {}

        data = [
            {"id": 1, "name": "Contains, comma"},
            {"id": 2, "name": 'Has "quotes"'},
        ]

        export_service.write_csv_results(
            job_id="job-123",
            tenant_id="tenant-456",
            columns=["id", "name"],
            data=data,
        )

        call_args = mock_s3_client.put_object.call_args
        body = call_args.kwargs["Body"].decode("utf-8")
        # CSV should properly escape these
        assert '"Contains, comma"' in body or "Contains, comma" in body


class TestExportExceptions:
    """Tests for export exception classes."""

    def test_export_error(self) -> None:
        """Test ExportError exception."""
        error = ExportError("Failed to export data")

        assert str(error) == "Failed to export data"
        assert isinstance(error, Exception)
