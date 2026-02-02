"""Unit tests for unified API Lambda handler.

Tests cover:
- Health check endpoint
- Root endpoint
- Routing to sub-handlers
"""

import json
from unittest.mock import MagicMock, patch

import pytest


def create_api_event(
    path: str = "/health",
    method: str = "GET",
    body: dict | None = None,
) -> dict:
    """Create a mock API Gateway event."""
    return {
        "httpMethod": method,
        "path": path,
        "resource": path,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body) if body else None,
        "requestContext": {
            "requestId": "test-request-123",
            "identity": {"sourceIp": "127.0.0.1"},
            "stage": "test",
        },
        "pathParameters": {},
        "queryStringParameters": {},
        "isBase64Encoded": False,
    }


@pytest.fixture
def mock_context():
    """Create a mock Lambda context."""
    context = MagicMock()
    context.function_name = "spectra-api"
    context.aws_request_id = "req-123"
    context.memory_limit_in_mb = 128
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:spectra-api"
    return context


class TestApiHandler:
    """Tests for unified API handler."""

    def test_health_check(self, mock_context):
        """Test health check endpoint returns healthy status."""
        from spectra.handlers.api import app

        event = create_api_event(path="/health", method="GET")
        result = app.resolve(event, mock_context)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "healthy"
        assert body["service"] == "redshift-spectra"

    def test_root_endpoint(self, mock_context):
        """Test root endpoint returns API information."""
        from spectra.handlers.api import app

        event = create_api_event(path="/", method="GET")
        result = app.resolve(event, mock_context)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["service"] == "redshift-spectra"
        assert body["version"] == "1.0.0"
        assert "endpoints" in body
        assert "/health" in body["endpoints"]["health"]

    def test_route_to_query_handler(self, mock_context):
        """Test routing to query handler for /v1/queries path."""
        from spectra.handlers.api import handler

        event = create_api_event(path="/v1/queries", method="POST")

        with patch("spectra.handlers.api.query_app") as mock_query_app:
            mock_query_app.resolve.return_value = {"statusCode": 200, "body": "{}"}
            handler(event, mock_context)

            mock_query_app.resolve.assert_called_once_with(event, mock_context)

    def test_route_to_bulk_handler(self, mock_context):
        """Test routing to bulk handler for /v1/bulk path."""
        from spectra.handlers.api import handler

        event = create_api_event(path="/v1/bulk/jobs", method="POST")

        with patch("spectra.handlers.api.bulk_app") as mock_bulk_app:
            mock_bulk_app.resolve.return_value = {"statusCode": 200, "body": "{}"}
            handler(event, mock_context)

            mock_bulk_app.resolve.assert_called_once_with(event, mock_context)

    def test_route_to_result_handler(self, mock_context):
        """Test routing to result handler for /v1/jobs/{id}/results path."""
        from spectra.handlers.api import handler

        event = create_api_event(path="/v1/jobs/job-123/results", method="GET")

        with patch("spectra.handlers.api.result_app") as mock_result_app:
            mock_result_app.resolve.return_value = {"statusCode": 200, "body": "{}"}
            handler(event, mock_context)

            mock_result_app.resolve.assert_called_once_with(event, mock_context)

    def test_route_to_status_handler(self, mock_context):
        """Test routing to status handler for /v1/jobs/{id} path."""
        from spectra.handlers.api import handler

        event = create_api_event(path="/v1/jobs/job-123", method="GET")

        with patch("spectra.handlers.api.status_app") as mock_status_app:
            mock_status_app.resolve.return_value = {"statusCode": 200, "body": "{}"}
            handler(event, mock_context)

            mock_status_app.resolve.assert_called_once_with(event, mock_context)

    def test_handler_resolves_health_check(self, mock_context):
        """Test handler resolves health check endpoint directly."""
        from spectra.handlers.api import handler

        event = create_api_event(path="/health", method="GET")
        result = handler(event, mock_context)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "healthy"


class TestApiHandlerEdgeCases:
    """Edge case tests for API handler."""

    def test_unknown_path(self, mock_context):
        """Test handling of unknown path."""
        from spectra.handlers.api import handler

        event = create_api_event(path="/unknown/path", method="GET")
        result = handler(event, mock_context)

        # Unknown paths handled by unified app (returns 404 or default)
        assert result["statusCode"] in [200, 404]

    def test_empty_path(self, mock_context):
        """Test handling of empty path defaults to root."""
        from spectra.handlers.api import handler

        event = create_api_event(path="", method="GET")
        result = handler(event, mock_context)

        # Empty path falls through to app.resolve
        assert result is not None
