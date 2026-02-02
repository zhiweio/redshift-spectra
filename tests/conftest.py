"""Pytest configuration and shared fixtures.

This module provides common fixtures for both unit and integration tests,
including AWS service mocking, sample data, and test utilities.
"""

import json
import os
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

# Set environment variables before importing spectra modules
os.environ.update(
    {
        "SPECTRA_AWS_REGION": "us-east-1",
        "SPECTRA_REDSHIFT_CLUSTER_ID": "test-cluster",
        "SPECTRA_REDSHIFT_DATABASE": "test_db",
        "SPECTRA_REDSHIFT_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
        "SPECTRA_S3_BUCKET_NAME": "test-bucket",
        "SPECTRA_DYNAMODB_TABLE_NAME": "spectra-jobs",
        "SPECTRA_DYNAMODB_SESSIONS_TABLE_NAME": "spectra-sessions",
        "SPECTRA_DYNAMODB_BULK_TABLE_NAME": "spectra-bulk-jobs",
        "SPECTRA_SQL_SECURITY_LEVEL": "standard",
        "POWERTOOLS_METRICS_NAMESPACE": "spectra-test",
    }
)


# =============================================================================
# AWS Mocking Fixtures
# =============================================================================


@pytest.fixture
def aws_credentials() -> None:
    """Mock AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def mock_dynamodb(aws_credentials: None) -> Generator[Any, None, None]:
    """Create mock DynamoDB tables."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        # Create jobs table
        dynamodb.create_table(
            TableName="spectra-jobs",
            KeySchema=[
                {"AttributeName": "job_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "tenant_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "gsi1-tenant",
                    "KeySchema": [
                        {"AttributeName": "tenant_id", "KeyType": "HASH"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Create sessions table
        dynamodb.create_table(
            TableName="spectra-sessions",
            KeySchema=[
                {"AttributeName": "session_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
                {"AttributeName": "tenant_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "gsi1-tenant",
                    "KeySchema": [
                        {"AttributeName": "tenant_id", "KeyType": "HASH"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Create bulk jobs table
        dynamodb.create_table(
            TableName="spectra-bulk-jobs",
            KeySchema=[
                {"AttributeName": "job_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "tenant_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "gsi1-tenant",
                    "KeySchema": [
                        {"AttributeName": "tenant_id", "KeyType": "HASH"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield dynamodb


@pytest.fixture
def mock_s3(aws_credentials: None) -> Generator[Any, None, None]:
    """Create mock S3 bucket."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        yield s3


@pytest.fixture
def mock_secrets_manager(aws_credentials: None) -> Generator[Any, None, None]:
    """Create mock Secrets Manager."""
    with mock_aws():
        sm = boto3.client("secretsmanager", region_name="us-east-1")
        sm.create_secret(
            Name="test-secret",
            SecretString=json.dumps(
                {
                    "username": "admin",
                    "password": "secret123",
                }
            ),
        )
        yield sm


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_tenant_context() -> dict[str, Any]:
    """Sample tenant context."""
    return {
        "tenant_id": "tenant-123",
        "db_user": "user_tenant_123",
        "db_group": "analytics_group",
        "permissions": ["read", "query"],
        "metadata": {"plan": "enterprise"},
    }


@pytest.fixture
def sample_api_gateway_event() -> dict[str, Any]:
    """Sample API Gateway event."""
    return {
        "httpMethod": "POST",
        "path": "/v1/queries",
        "headers": {
            "Content-Type": "application/json",
            "X-Tenant-ID": "tenant-123",
            "X-DB-User": "user_tenant_123",
            "X-API-Key": "test-api-key",
        },
        "body": json.dumps(
            {
                "sql": "SELECT * FROM sales WHERE tenant_id = 'tenant-123' LIMIT 100",
                "output_format": "json",
                "async": True,
            }
        ),
        "requestContext": {
            "requestId": "request-123",
            "identity": {
                "sourceIp": "192.168.1.1",
            },
            "authorizer": {
                "claims": {
                    "tenant_id": "tenant-123",
                    "db_user": "user_tenant_123",
                },
            },
        },
        "queryStringParameters": {},
        "pathParameters": {},
        "isBase64Encoded": False,
    }


@pytest.fixture
def sample_query_request() -> dict[str, Any]:
    """Sample query request body."""
    return {
        "sql": "SELECT id, name, amount FROM orders WHERE status = 'active' LIMIT 1000",
        "output_format": "json",
        "async": True,
        "timeout_seconds": 300,
        "metadata": {"source": "analytics_dashboard"},
    }


@pytest.fixture
def sample_bulk_job_request() -> dict[str, Any]:
    """Sample bulk job creation request."""
    return {
        "operation": "query",
        "query": "SELECT * FROM large_table WHERE date >= '2024-01-01'",
        "content_type": "CSV",
        "compression": "GZIP",
    }


@pytest.fixture
def sample_job_data() -> dict[str, Any]:
    """Sample job data for DynamoDB."""
    now = datetime.now(UTC)
    return {
        "job_id": "job-abc123def456",
        "tenant_id": "tenant-123",
        "status": "QUEUED",
        "sql": "SELECT * FROM test_table LIMIT 10",
        "sql_hash": "a1b2c3d4e5f6",
        "db_user": "user_tenant_123",
        "db_group": "analytics",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "output_format": "json",
        "async_mode": True,
        "timeout_seconds": 900,
        "ttl": int((now.timestamp()) + 86400 * 7),
    }


# =============================================================================
# Mock Service Fixtures
# =============================================================================


@pytest.fixture
def mock_redshift_client() -> Generator[MagicMock, None, None]:
    """Mock Redshift Data API client."""
    with patch("boto3.client") as mock_client:
        redshift_mock = MagicMock()
        redshift_mock.execute_statement.return_value = {
            "Id": "statement-123",
            "SessionId": "session-456",
        }
        redshift_mock.describe_statement.return_value = {
            "Id": "statement-123",
            "Status": "FINISHED",
            "ResultRows": 100,
            "ResultSize": 5000,
        }
        redshift_mock.get_statement_result.return_value = {
            "ColumnMetadata": [
                {"name": "id", "typeName": "int4"},
                {"name": "name", "typeName": "varchar"},
            ],
            "Records": [
                [{"longValue": 1}, {"stringValue": "Test"}],
                [{"longValue": 2}, {"stringValue": "Test2"}],
            ],
            "TotalNumRows": 2,
        }
        mock_client.return_value = redshift_mock
        yield redshift_mock


@pytest.fixture
def lambda_context() -> MagicMock:
    """Mock Lambda context."""
    context = MagicMock()
    context.function_name = "spectra-query-handler"
    context.memory_limit_in_mb = 256
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:spectra"
    context.aws_request_id = "request-123-456-789"
    context.get_remaining_time_in_millis.return_value = 30000
    return context


# =============================================================================
# SQL Test Fixtures
# =============================================================================


@pytest.fixture
def valid_sql_queries() -> list[str]:
    """List of valid SQL queries for testing."""
    return [
        "SELECT * FROM users LIMIT 100",
        "SELECT id, name, email FROM customers WHERE active = true",
        "SELECT COUNT(*) FROM orders GROUP BY status",
        "SELECT a.id, b.name FROM table_a a JOIN table_b b ON a.id = b.id",
        "WITH cte AS (SELECT * FROM temp) SELECT * FROM cte",
        "SELECT UPPER(name), LOWER(email) FROM users",
        "SELECT DATE_TRUNC('month', created_at), SUM(amount) FROM sales GROUP BY 1",
        "SELECT * FROM products WHERE price BETWEEN 10 AND 100",
        "SELECT DISTINCT category FROM items ORDER BY category",
        "SELECT id, COALESCE(nickname, name) as display_name FROM users",
    ]


@pytest.fixture
def invalid_sql_queries() -> list[tuple[str, str]]:
    """List of invalid SQL queries with expected error patterns."""
    return [
        ("DROP TABLE users", "Forbidden statement"),
        ("DELETE FROM orders WHERE id = 1", "Forbidden statement"),
        ("INSERT INTO logs VALUES (1, 'test')", "Forbidden statement"),
        ("UPDATE users SET active = false", "Forbidden statement"),
        ("CREATE TABLE hack (id int)", "Forbidden statement"),
        ("SELECT * FROM users; DROP TABLE users", "Stacked query"),
        ("SELECT * FROM pg_catalog.pg_tables", "system object"),
        ("SELECT * FROM users WHERE 1=1--", "comment"),
        ("SELECT * FROM users UNION SELECT * FROM admin", "UNION"),
    ]


@pytest.fixture
def injection_attempts() -> list[str]:
    """List of SQL injection attempts."""
    return [
        "SELECT * FROM users WHERE id = 1; DROP TABLE users--",
        "SELECT * FROM users WHERE name = '' OR '1'='1'",
        "SELECT * FROM users WHERE id = 1 UNION SELECT password FROM admin",
        "SELECT * FROM users; EXEC xp_cmdshell('dir')",
        "SELECT * FROM users WHERE id = 1/*comment*/",
        "SELECT BENCHMARK(1000000, SHA1('test'))",
        "SELECT * FROM users WHERE id = 0x31",
        "SELECT CHAR(65, 66, 67)",
        "SELECT PG_SLEEP(10)",
    ]


# =============================================================================
# Test Utilities
# =============================================================================


def create_api_event(
    method: str = "GET",
    path: str = "/v1/jobs",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    path_params: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
    tenant_id: str = "tenant-123",
    db_user: str = "user_tenant_123",
) -> dict[str, Any]:
    """Create a mock API Gateway event.

    Args:
        method: HTTP method
        path: Request path
        body: Request body dict
        headers: Additional headers
        path_params: Path parameters
        query_params: Query string parameters
        tenant_id: Tenant ID for context
        db_user: Database user for context

    Returns:
        Mock API Gateway event dict
    """
    default_headers = {
        "Content-Type": "application/json",
        "X-Tenant-ID": tenant_id,
        "X-DB-User": db_user,
    }
    if headers:
        default_headers.update(headers)

    return {
        "httpMethod": method,
        "path": path,
        "headers": default_headers,
        "body": json.dumps(body) if body else None,
        "requestContext": {
            "requestId": f"test-request-{datetime.now(UTC).timestamp()}",
            "identity": {"sourceIp": "127.0.0.1"},
        },
        "pathParameters": path_params or {},
        "queryStringParameters": query_params or {},
        "isBase64Encoded": False,
    }
