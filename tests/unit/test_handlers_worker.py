"""Unit tests for Worker Lambda handler.

Tests cover:
- Query job processing
- Bulk job processing
- SQS event processing
- DynamoDB Stream event processing
- Direct invocation
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_context():
    """Create a mock Lambda context."""
    context = MagicMock()
    context.function_name = "spectra-worker"
    context.aws_request_id = "req-123"
    return context


class TestProcessQueryJob:
    """Tests for query job processing function."""

    def test_process_query_job_success(self):
        """Test successful query job processing."""
        from spectra.handlers.worker import process_query_job
        from spectra.models.job import Job, JobStatus

        now = datetime.now(UTC)
        mock_job = Job(
            job_id="job-123",
            tenant_id="tenant-123",
            status=JobStatus.SUBMITTED,
            sql="SELECT * FROM users",
            sql_hash="abc123",
            db_user="user_tenant_123",
            statement_id="stmt-456",
            created_at=now,
            updated_at=now,
        )

        with (
            patch("spectra.handlers.worker.JobService") as mock_job_svc,
            patch("spectra.handlers.worker.RedshiftService") as mock_rs_svc,
            patch("spectra.handlers.worker.ExportService") as mock_export_svc,
        ):
            mock_job_svc.return_value.get_job.return_value = mock_job
            mock_rs_svc.return_value.describe_statement.return_value = {"status": "FINISHED"}
            mock_rs_svc.return_value.get_statement_result.return_value = {
                "records": [{"id": 1}, {"id": 2}],
                "column_info": [{"name": "id", "type": "int4"}],
            }
            mock_export_svc.return_value.export_results.return_value = {
                "location": "s3://bucket/path/results.json",
                "size_bytes": 1024,
            }

            result = process_query_job("job-123", "tenant-123")

            assert result["status"] == "completed"
            assert "location" in result
            mock_job_svc.return_value.update_job_completed.assert_called_once()

    def test_process_query_job_failed_status(self):
        """Test query job processing when Redshift reports failure."""
        from spectra.handlers.worker import process_query_job
        from spectra.models.job import Job, JobStatus

        now = datetime.now(UTC)
        mock_job = Job(
            job_id="job-123",
            tenant_id="tenant-123",
            status=JobStatus.SUBMITTED,
            sql="SELECT * FROM users",
            sql_hash="abc123",
            db_user="user_tenant_123",
            statement_id="stmt-456",
            created_at=now,
            updated_at=now,
        )

        with (
            patch("spectra.handlers.worker.JobService") as mock_job_svc,
            patch("spectra.handlers.worker.RedshiftService") as mock_rs_svc,
            patch("spectra.handlers.worker.ExportService"),
        ):
            mock_job_svc.return_value.get_job.return_value = mock_job
            mock_rs_svc.return_value.describe_statement.return_value = {
                "status": "FAILED",
                "error": "Column not found",
            }

            result = process_query_job("job-123", "tenant-123")

            assert result["status"] == "failed"
            assert "error" in result
            mock_job_svc.return_value.update_job_failed.assert_called_once()

    def test_process_query_job_skips_completed(self):
        """Test that already completed jobs are skipped."""
        from spectra.handlers.worker import process_query_job
        from spectra.models.job import Job, JobStatus

        now = datetime.now(UTC)
        mock_job = Job(
            job_id="job-123",
            tenant_id="tenant-123",
            status=JobStatus.COMPLETED,
            sql="SELECT * FROM users",
            sql_hash="abc123",
            db_user="user_tenant_123",
            created_at=now,
            updated_at=now,
        )

        with (
            patch("spectra.handlers.worker.JobService") as mock_job_svc,
            patch("spectra.handlers.worker.RedshiftService"),
            patch("spectra.handlers.worker.ExportService"),
        ):
            mock_job_svc.return_value.get_job.return_value = mock_job

            result = process_query_job("job-123", "tenant-123")

            assert result["status"] == "skipped"
            assert "COMPLETED" in result["reason"]

    def test_process_query_job_no_statement_id(self):
        """Test handling of job without statement ID."""
        from spectra.handlers.worker import process_query_job
        from spectra.models.job import Job, JobStatus

        now = datetime.now(UTC)
        mock_job = Job(
            job_id="job-123",
            tenant_id="tenant-123",
            status=JobStatus.QUEUED,
            sql="SELECT * FROM users",
            sql_hash="abc123",
            db_user="user_tenant_123",
            statement_id=None,
            created_at=now,
            updated_at=now,
        )

        with (
            patch("spectra.handlers.worker.JobService") as mock_job_svc,
            patch("spectra.handlers.worker.RedshiftService"),
            patch("spectra.handlers.worker.ExportService"),
        ):
            mock_job_svc.return_value.get_job.return_value = mock_job

            result = process_query_job("job-123", "tenant-123")

            assert result["status"] == "pending"
            assert "No statement ID" in result["reason"]


class TestProcessBulkJob:
    """Tests for bulk job processing function."""

    def test_process_bulk_job_success(self):
        """Test successful bulk job processing."""
        from spectra.handlers.worker import process_bulk_job
        from spectra.models.bulk import BulkJob, BulkJobState, BulkOperation

        mock_job = MagicMock(spec=BulkJob)
        mock_job.job_id = "bulk-123"
        mock_job.tenant_id = "tenant-123"
        mock_job.state = BulkJobState.UPLOAD_COMPLETE.value
        mock_job.operation = BulkOperation.QUERY

        with patch("spectra.handlers.worker.BulkJobService") as mock_bulk_svc:
            mock_bulk_svc.return_value.get_job.return_value = mock_job

            result = process_bulk_job("bulk-123", "tenant-123")

            assert result["status"] == "completed"
            mock_bulk_svc.return_value.update_job_state.assert_called()

    def test_process_bulk_job_skips_wrong_state(self):
        """Test that jobs in wrong state are skipped."""
        from spectra.handlers.worker import process_bulk_job
        from spectra.models.bulk import BulkJob, BulkJobState, BulkOperation

        mock_job = MagicMock(spec=BulkJob)
        mock_job.job_id = "bulk-123"
        mock_job.tenant_id = "tenant-123"
        mock_job.state = BulkJobState.FAILED.value
        mock_job.operation = BulkOperation.QUERY

        with patch("spectra.handlers.worker.BulkJobService") as mock_bulk_svc:
            mock_bulk_svc.return_value.get_job.return_value = mock_job

            result = process_bulk_job("bulk-123", "tenant-123")

            assert result["status"] == "skipped"


class TestProcessSQSRecord:
    """Tests for SQS record processing."""

    def test_process_sqs_record_query(self):
        """Test processing SQS record for query job."""
        from spectra.handlers.worker import process_sqs_record

        record = {
            "body": json.dumps(
                {
                    "job_type": "query",
                    "job_id": "job-123",
                    "tenant_id": "tenant-123",
                }
            )
        }

        with patch("spectra.handlers.worker.process_query_job") as mock_process:
            mock_process.return_value = {"status": "completed"}

            result = process_sqs_record(record)

            assert result["status"] == "completed"
            mock_process.assert_called_once_with("job-123", "tenant-123")

    def test_process_sqs_record_bulk(self):
        """Test processing SQS record for bulk job."""
        from spectra.handlers.worker import process_sqs_record

        record = {
            "body": json.dumps(
                {
                    "job_type": "bulk",
                    "job_id": "bulk-123",
                    "tenant_id": "tenant-123",
                }
            )
        }

        with patch("spectra.handlers.worker.process_bulk_job") as mock_process:
            mock_process.return_value = {"status": "completed"}

            result = process_sqs_record(record)

            assert result["status"] == "completed"
            mock_process.assert_called_once_with("bulk-123", "tenant-123")

    def test_process_sqs_record_missing_fields(self):
        """Test processing SQS record with missing fields."""
        from spectra.handlers.worker import process_sqs_record

        record = {"body": json.dumps({"job_type": "query"})}  # Missing job_id and tenant_id

        result = process_sqs_record(record)

        assert result["status"] == "error"
        assert "Missing required fields" in result["reason"]


class TestProcessDynamoDBRecord:
    """Tests for DynamoDB Stream record processing."""

    def test_process_dynamodb_record_insert(self):
        """Test processing DynamoDB INSERT event."""
        from spectra.handlers.worker import process_dynamodb_record

        record = {
            "eventName": "INSERT",
            "dynamodb": {
                "NewImage": {
                    "job_id": {"S": "job-123"},
                    "tenant_id": {"S": "tenant-123"},
                    "status": {"S": "PENDING"},
                }
            },
        }

        with patch("spectra.handlers.worker.process_query_job") as mock_process:
            mock_process.return_value = {"status": "completed"}

            result = process_dynamodb_record(record)

            assert result["status"] == "completed"

    def test_process_dynamodb_record_skips_delete(self):
        """Test that DELETE events are skipped."""
        from spectra.handlers.worker import process_dynamodb_record

        record = {
            "eventName": "REMOVE",
            "dynamodb": {},
        }

        result = process_dynamodb_record(record)

        assert result["status"] == "skipped"

    def test_process_dynamodb_record_skips_non_pending(self):
        """Test that non-PENDING jobs are skipped."""
        from spectra.handlers.worker import process_dynamodb_record

        record = {
            "eventName": "MODIFY",
            "dynamodb": {
                "NewImage": {
                    "job_id": {"S": "job-123"},
                    "tenant_id": {"S": "tenant-123"},
                    "status": {"S": "COMPLETED"},
                }
            },
        }

        result = process_dynamodb_record(record)

        assert result["status"] == "skipped"


class TestWorkerHandler:
    """Tests for worker Lambda handler."""

    def test_handler_sqs_event(self, mock_context):
        """Test handler with SQS event."""
        from spectra.handlers.worker import handler

        event = {
            "Records": [
                {
                    "eventSource": "aws:sqs",
                    "body": json.dumps(
                        {
                            "job_type": "query",
                            "job_id": "job-123",
                            "tenant_id": "tenant-123",
                        }
                    ),
                }
            ]
        }

        with patch("spectra.handlers.worker.process_sqs_record") as mock_process:
            mock_process.return_value = {"status": "completed"}

            result = handler(event, mock_context)

            assert result["status"] == "ok"
            assert result["processed"] == 1
            assert result["completed"] == 1

    def test_handler_dynamodb_event(self, mock_context):
        """Test handler with DynamoDB Streams event."""
        from spectra.handlers.worker import handler

        event = {
            "Records": [
                {
                    "eventSource": "aws:dynamodb",
                    "eventName": "INSERT",
                    "dynamodb": {
                        "NewImage": {
                            "job_id": {"S": "job-123"},
                            "tenant_id": {"S": "tenant-123"},
                            "status": {"S": "PENDING"},
                        }
                    },
                }
            ]
        }

        with patch("spectra.handlers.worker.process_dynamodb_record") as mock_process:
            mock_process.return_value = {"status": "completed"}

            result = handler(event, mock_context)

            assert result["status"] == "ok"
            assert result["processed"] == 1

    def test_handler_direct_invocation(self, mock_context):
        """Test handler with direct invocation."""
        from spectra.handlers.worker import handler

        event = {
            "job_id": "job-123",
            "tenant_id": "tenant-123",
            "job_type": "query",
        }

        with patch("spectra.handlers.worker.process_query_job") as mock_process:
            mock_process.return_value = {"status": "completed"}

            result = handler(event, mock_context)

            assert result["status"] == "ok"
            assert result["completed"] == 1
            mock_process.assert_called_once_with("job-123", "tenant-123")

    def test_handler_unknown_event_format(self, mock_context):
        """Test handler with unknown event format."""
        from spectra.handlers.worker import handler

        event = {"unknown": "format"}

        result = handler(event, mock_context)

        assert result["status"] == "error"
        assert "Unknown event format" in result["reason"]

    def test_handler_multiple_records(self, mock_context):
        """Test handler with multiple SQS records."""
        from spectra.handlers.worker import handler

        event = {
            "Records": [
                {
                    "eventSource": "aws:sqs",
                    "body": json.dumps(
                        {"job_type": "query", "job_id": "job-1", "tenant_id": "tenant-1"}
                    ),
                },
                {
                    "eventSource": "aws:sqs",
                    "body": json.dumps(
                        {"job_type": "query", "job_id": "job-2", "tenant_id": "tenant-2"}
                    ),
                },
            ]
        }

        with patch("spectra.handlers.worker.process_sqs_record") as mock_process:
            mock_process.side_effect = [
                {"status": "completed"},
                {"status": "failed", "error": "Error"},
            ]

            result = handler(event, mock_context)

            assert result["status"] == "ok"
            assert result["processed"] == 2
            assert result["completed"] == 1
            assert result["failed"] == 1
