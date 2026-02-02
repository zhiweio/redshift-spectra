"""LocalStack Integration Tests for Real API Endpoints.

This module tests the actual deployed API Gateway endpoints in LocalStack,
simulating real client interactions with the Redshift Spectra API.

Prerequisites:
    - LocalStack running: `make localstack-start`
    - Infrastructure deployed: `make tg-apply-local`
    - Lambda code uploaded: `make package-lambda-fat` + update Lambda code

Usage:
    # Run all tests (skips Redshift-dependent tests on free version)
    pytest tests/integration/test_localstack_api.py -v -s

    # Run with Redshift tests enabled (requires LocalStack Pro)
    LOCALSTACK_PRO=1 pytest tests/integration/test_localstack_api.py -v -s

Environment Variables:
    LOCALSTACK_API_GATEWAY_URL: Override the API Gateway URL
    LOCALSTACK_PRO: Set to "1" to enable Redshift Data API tests
    JWT_SECRET: Override the JWT secret (default: local testing secret)
"""

import os
import subprocess
import time

import jwt
import pytest
import requests

# =============================================================================
# Configuration
# =============================================================================

JWT_SECRET = os.getenv("JWT_SECRET", "local-jwt-secret-key-for-testing-only-123456")
JWT_ISSUER = os.getenv("JWT_ISSUER", "redshift-spectra-local")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "redshift-spectra-api")

TEST_TENANT_ID = "test-tenant-001"
TEST_DB_USER = "tenant_test_user"
TEST_DB_GROUP = "tenant_test_group"

REQUEST_TIMEOUT = 30
LOCALSTACK_PRO = os.getenv("LOCALSTACK_PRO", "").lower() in ("1", "true", "yes")


def get_api_gateway_url() -> str:
    env_url = os.getenv("LOCALSTACK_API_GATEWAY_URL")
    if env_url:
        return env_url
    try:
        result = subprocess.run(
            [
                "awslocal",
                "apigateway",
                "get-rest-apis",
                "--query",
                "items[?name==`redshift-spectra-local-api`].id",
                "--output",
                "text",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        api_id = result.stdout.strip()
        if api_id:
            return f"http://localhost:4566/restapis/{api_id}/local/_user_request_"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "http://localhost:4566/restapis/default/local/_user_request_"


def is_localstack_running() -> bool:
    try:
        response = requests.get("http://localhost:4566/_localstack/health", timeout=5)
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        return False


def generate_jwt_token(
    tenant_id: str = TEST_TENANT_ID,
    db_user: str = TEST_DB_USER,
    db_group: str = TEST_DB_GROUP,
    expires_in: int = 3600,
) -> str:
    payload = {
        "sub": tenant_id,
        "tenant_id": tenant_id,
        "db_user": db_user,
        "db_group": db_group,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def invoke_lambda(
    function_name: str, payload: str, output_file: str
) -> subprocess.CompletedProcess[str]:
    """Invoke a Lambda function via awslocal CLI.

    Args:
        function_name: Name of the Lambda function
        payload: JSON payload string
        output_file: Path to write response

    Returns:
        CompletedProcess result
    """
    return subprocess.run(
        [
            "awslocal",
            "lambda",
            "invoke",
            "--function-name",
            function_name,
            "--cli-binary-format",
            "raw-in-base64-out",
            "--payload",
            payload,
            output_file,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def read_json_file(filepath: str) -> dict:
    """Read JSON from a file using Path.

    Args:
        filepath: Path to the JSON file

    Returns:
        Parsed JSON as dict
    """
    import json
    from pathlib import Path as LocalPath

    with LocalPath(filepath).open() as f:
        return json.load(f)  # type: ignore[return-value]


pytestmark = pytest.mark.skipif(
    not is_localstack_running(),
    reason="LocalStack is not running. Start with: make localstack-start",
)

requires_redshift = pytest.mark.skipif(
    not LOCALSTACK_PRO,
    reason="Requires LocalStack Pro for Redshift Data API. Set LOCALSTACK_PRO=1 to enable.",
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def api_base_url() -> str:
    return get_api_gateway_url()


@pytest.fixture
def jwt_token() -> str:
    return generate_jwt_token()


@pytest.fixture
def expired_jwt_token() -> str:
    return generate_jwt_token(expires_in=-3600)


@pytest.fixture
def invalid_jwt_token() -> str:
    payload = {
        "sub": TEST_TENANT_ID,
        "tenant_id": TEST_TENANT_ID,
        "db_user": TEST_DB_USER,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, "wrong-secret", algorithm="HS256")


@pytest.fixture
def default_headers(jwt_token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {jwt_token}",
        "X-Tenant-ID": TEST_TENANT_ID,
    }


# =============================================================================
# Health Check Tests
# =============================================================================


class TestLocalStackHealth:
    def test_localstack_is_running(self) -> None:
        response = requests.get("http://localhost:4566/_localstack/health", timeout=5)
        assert response.status_code == 200
        health = response.json()
        assert "services" in health
        services = health["services"]
        assert services.get("lambda") in ["running", "available"]
        assert services.get("dynamodb") in ["running", "available"]

    def test_api_gateway_accessible(self, api_base_url: str) -> None:
        print(f"API Gateway URL: {api_base_url}")
        assert "localhost:4566" in api_base_url


# =============================================================================
# Lambda Direct Invocation Tests
# =============================================================================


class TestLambdaDirectInvocation:
    def test_api_lambda_health_check(self) -> None:
        import json

        payload = json.dumps({"httpMethod": "GET", "path": "/health", "headers": {}})
        result = invoke_lambda(
            "redshift-spectra-local-api",
            payload,
            "/tmp/lambda-health-response.json",
        )
        assert result.returncode == 0, f"Lambda invoke failed: {result.stderr}"
        response = read_json_file("/tmp/lambda-health-response.json")
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "healthy"

    def test_authorizer_lambda_valid_token(self, jwt_token: str) -> None:
        import json

        payload = json.dumps(
            {
                "authorizationToken": f"Bearer {jwt_token}",
                "methodArn": "arn:aws:execute-api:us-east-1:000000000000:api/local/POST/v1/queries",
            }
        )
        result = invoke_lambda(
            "redshift-spectra-local-authorizer",
            payload,
            "/tmp/lambda-auth-response.json",
        )
        assert result.returncode == 0
        response = read_json_file("/tmp/lambda-auth-response.json")
        assert response["principalId"] == TEST_TENANT_ID
        assert response["policyDocument"]["Statement"][0]["Effect"] == "Allow"

    def test_authorizer_lambda_invalid_token(self, invalid_jwt_token: str) -> None:
        import json

        payload = json.dumps(
            {
                "authorizationToken": f"Bearer {invalid_jwt_token}",
                "methodArn": "arn:aws:execute-api:us-east-1:000000000000:api/local/POST/v1/queries",
            }
        )
        result = invoke_lambda(
            "redshift-spectra-local-authorizer",
            payload,
            "/tmp/lambda-auth-invalid.json",
        )
        assert result.returncode == 0
        response = read_json_file("/tmp/lambda-auth-invalid.json")
        assert response["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    def test_authorizer_lambda_expired_token(self, expired_jwt_token: str) -> None:
        import json

        payload = json.dumps(
            {
                "authorizationToken": f"Bearer {expired_jwt_token}",
                "methodArn": "arn:aws:execute-api:us-east-1:000000000000:api/local/POST/v1/queries",
            }
        )
        result = invoke_lambda(
            "redshift-spectra-local-authorizer",
            payload,
            "/tmp/lambda-auth-expired.json",
        )
        assert result.returncode == 0
        response = read_json_file("/tmp/lambda-auth-expired.json")
        assert response["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    def test_api_lambda_query_with_authorizer_context(self) -> None:
        import json

        payload = json.dumps(
            {
                "httpMethod": "POST",
                "path": "/v1/queries",
                "headers": {"Content-Type": "application/json"},
                "requestContext": {
                    "requestId": "test-123",
                    "identity": {"sourceIp": "127.0.0.1"},
                    "authorizer": {
                        "tenant_id": TEST_TENANT_ID,
                        "db_user": TEST_DB_USER,
                        "db_group": TEST_DB_GROUP,
                    },
                },
                "body": json.dumps({"sql": "SELECT 1 as test"}),
            }
        )
        result = invoke_lambda(
            "redshift-spectra-local-api",
            payload,
            "/tmp/lambda-query-response.json",
        )
        assert result.returncode == 0
        response = read_json_file("/tmp/lambda-query-response.json")
        body = json.loads(response["body"])
        assert "job_id" in body
        assert body["status"] in ["QUEUED", "SUBMITTED", "FAILED"]

    def test_api_lambda_bulk_job_create(self) -> None:
        import json

        payload = json.dumps(
            {
                "httpMethod": "POST",
                "path": "/v1/bulk/jobs",
                "headers": {"Content-Type": "application/json"},
                "requestContext": {
                    "requestId": "bulk-test-123",
                    "identity": {"sourceIp": "127.0.0.1"},
                    "authorizer": {
                        "tenant_id": TEST_TENANT_ID,
                        "db_user": TEST_DB_USER,
                        "db_group": TEST_DB_GROUP,
                    },
                },
                "body": json.dumps(
                    {"operation": "query", "query": "SELECT * FROM test_table LIMIT 10"}
                ),
            }
        )
        result = invoke_lambda(
            "redshift-spectra-local-api",
            payload,
            "/tmp/lambda-bulk-response.json",
        )
        assert result.returncode == 0
        response = read_json_file("/tmp/lambda-bulk-response.json")
        assert response["statusCode"] == 201
        body = json.loads(response["body"])
        assert "id" in body
        assert body["operation"] == "query"


# =============================================================================
# DynamoDB Persistence Tests
# =============================================================================


class TestDynamoDBPersistence:
    def test_job_persisted_to_dynamodb(self) -> None:
        import json

        payload = json.dumps(
            {
                "httpMethod": "POST",
                "path": "/v1/queries",
                "headers": {"Content-Type": "application/json"},
                "requestContext": {
                    "requestId": "persist-test",
                    "identity": {"sourceIp": "127.0.0.1"},
                    "authorizer": {
                        "tenant_id": TEST_TENANT_ID,
                        "db_user": TEST_DB_USER,
                        "db_group": TEST_DB_GROUP,
                    },
                },
                "body": json.dumps({"sql": "SELECT 1 as persist_test"}),
            }
        )
        result = invoke_lambda(
            "redshift-spectra-local-api",
            payload,
            "/tmp/lambda-persist.json",
        )
        assert result.returncode == 0
        response = read_json_file("/tmp/lambda-persist.json")
        body = json.loads(response["body"])
        job_id = body.get("job_id")
        assert job_id is not None

        scan_result = subprocess.run(
            [
                "awslocal",
                "dynamodb",
                "scan",
                "--table-name",
                "redshift-spectra-local-jobs",
                "--filter-expression",
                "job_id = :jid",
                "--expression-attribute-values",
                json.dumps({":jid": {"S": job_id}}),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert scan_result.returncode == 0
        scan_data = json.loads(scan_result.stdout)
        assert scan_data["Count"] >= 1


# =============================================================================
# Query API Tests (Requires LocalStack Pro for Redshift)
# =============================================================================


class TestQueryAPI:
    @requires_redshift
    def test_query_execution_with_redshift(self, api_base_url: str, default_headers: dict) -> None:
        response = requests.post(
            f"{api_base_url}/v1/queries",
            json={"sql": "SELECT 1 as test_value", "output_format": "json"},
            headers=default_headers,
            timeout=REQUEST_TIMEOUT,
        )
        print(f"Query response: {response.status_code} - {response.text[:200]}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "COMPLETED"

    def test_query_with_invalid_sql_rejected(self) -> None:
        import json

        payload = json.dumps(
            {
                "httpMethod": "POST",
                "path": "/v1/queries",
                "headers": {"Content-Type": "application/json"},
                "requestContext": {
                    "requestId": "invalid-sql",
                    "identity": {"sourceIp": "127.0.0.1"},
                    "authorizer": {
                        "tenant_id": TEST_TENANT_ID,
                        "db_user": TEST_DB_USER,
                        "db_group": TEST_DB_GROUP,
                    },
                },
                "body": json.dumps({"sql": "DROP TABLE users"}),
            }
        )
        result = invoke_lambda(
            "redshift-spectra-local-api",
            payload,
            "/tmp/lambda-invalid-sql.json",
        )
        assert result.returncode == 0
        response = read_json_file("/tmp/lambda-invalid-sql.json")
        assert response["statusCode"] == 400


# =============================================================================
# Bulk API Tests
# =============================================================================


class TestBulkAPI:
    def test_create_bulk_export_job(self) -> None:
        import json

        payload = json.dumps(
            {
                "httpMethod": "POST",
                "path": "/v1/bulk/jobs",
                "headers": {"Content-Type": "application/json"},
                "requestContext": {
                    "requestId": "bulk-export",
                    "identity": {"sourceIp": "127.0.0.1"},
                    "authorizer": {
                        "tenant_id": TEST_TENANT_ID,
                        "db_user": TEST_DB_USER,
                        "db_group": TEST_DB_GROUP,
                    },
                },
                "body": json.dumps(
                    {
                        "operation": "query",
                        "query": "SELECT * FROM sales LIMIT 100",
                        "content_type": "CSV",
                    }
                ),
            }
        )
        result = invoke_lambda(
            "redshift-spectra-local-api",
            payload,
            "/tmp/lambda-bulk-export.json",
        )
        assert result.returncode == 0
        response = read_json_file("/tmp/lambda-bulk-export.json")
        assert response["statusCode"] == 201


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    def test_invalid_json_body(self) -> None:
        import json

        payload = json.dumps(
            {
                "httpMethod": "POST",
                "path": "/v1/queries",
                "headers": {"Content-Type": "application/json"},
                "requestContext": {
                    "requestId": "invalid-json",
                    "identity": {"sourceIp": "127.0.0.1"},
                    "authorizer": {
                        "tenant_id": TEST_TENANT_ID,
                        "db_user": TEST_DB_USER,
                        "db_group": TEST_DB_GROUP,
                    },
                },
                "body": "not valid json{",
            }
        )
        result = invoke_lambda(
            "redshift-spectra-local-api",
            payload,
            "/tmp/lambda-invalid-json.json",
        )
        assert result.returncode == 0
        response = read_json_file("/tmp/lambda-invalid-json.json")
        assert response["statusCode"] == 400

    def test_missing_required_fields(self) -> None:
        import json

        payload = json.dumps(
            {
                "httpMethod": "POST",
                "path": "/v1/queries",
                "headers": {"Content-Type": "application/json"},
                "requestContext": {
                    "requestId": "missing-fields",
                    "identity": {"sourceIp": "127.0.0.1"},
                    "authorizer": {
                        "tenant_id": TEST_TENANT_ID,
                        "db_user": TEST_DB_USER,
                        "db_group": TEST_DB_GROUP,
                    },
                },
                "body": json.dumps({}),
            }
        )
        result = invoke_lambda(
            "redshift-spectra-local-api",
            payload,
            "/tmp/lambda-missing-fields.json",
        )
        assert result.returncode == 0
        response = read_json_file("/tmp/lambda-missing-fields.json")
        assert response["statusCode"] == 400

    def test_missing_tenant_context(self) -> None:
        import json

        payload = json.dumps(
            {
                "httpMethod": "POST",
                "path": "/v1/queries",
                "headers": {"Content-Type": "application/json"},
                "requestContext": {"requestId": "no-tenant", "identity": {"sourceIp": "127.0.0.1"}},
                "body": json.dumps({"sql": "SELECT 1"}),
            }
        )
        result = invoke_lambda(
            "redshift-spectra-local-api",
            payload,
            "/tmp/lambda-no-tenant.json",
        )
        assert result.returncode == 0
        response = read_json_file("/tmp/lambda-no-tenant.json")
        assert response["statusCode"] == 401


# =============================================================================
# Performance Tests
# =============================================================================


class TestPerformance:
    def test_lambda_cold_start_time(self) -> None:
        import json

        payload = json.dumps({"httpMethod": "GET", "path": "/health", "headers": {}})
        start = time.time()
        result = invoke_lambda(
            "redshift-spectra-local-api",
            payload,
            "/tmp/lambda-perf.json",
        )
        elapsed = time.time() - start
        assert result.returncode == 0
        print(f"Lambda invocation time: {elapsed:.3f}s")
        assert elapsed < 30.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
