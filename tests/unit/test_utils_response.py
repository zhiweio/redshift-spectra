"""Unit tests for response utilities.

Tests for API response building utilities that return aws_lambda_powertools Response objects.
"""

import json

from aws_lambda_powertools.event_handler import Response

from spectra.utils.response import (
    accepted_response,
    build_response,
    created_response,
    error_response,
    forbidden_response,
    internal_error_response,
    not_found_response,
    rate_limit_response,
    success_response,
    unauthorized_response,
    validation_error_response,
)

# =============================================================================
# Build Response Tests
# =============================================================================


class TestBuildResponse:
    """Tests for build_response function."""

    def test_basic_response(self) -> None:
        """Test building a basic response."""
        response = build_response(200, {"message": "Hello"})

        assert isinstance(response, Response)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["message"] == "Hello"

    def test_default_headers_only_content_type(self) -> None:
        """Test that only Content-Type is set when no custom headers provided."""
        response = build_response(200)

        # CORS headers are handled at the resolver level, not in response utilities
        # Only Content-Type should be present by default
        assert response.headers.get("Content-Type") == "application/json"
        # No CORS headers should be added by response utilities
        assert "Access-Control-Allow-Origin" not in response.headers

    def test_content_type_json(self) -> None:
        """Test that Content-Type is set to JSON."""
        response = build_response(200)

        assert response.content_type == "application/json"

    def test_custom_headers(self) -> None:
        """Test that custom headers are merged."""
        response = build_response(
            200,
            {"data": "test"},
            headers={"X-Custom-Header": "custom-value"},
        )

        assert response.headers["X-Custom-Header"] == "custom-value"
        assert response.content_type == "application/json"

    def test_none_body(self) -> None:
        """Test response with None body."""
        response = build_response(204)

        assert response.body == ""

    def test_list_body(self) -> None:
        """Test response with list body."""
        response = build_response(200, [1, 2, 3])

        body = json.loads(response.body)
        assert body == [1, 2, 3]

    def test_json_serialization(self) -> None:
        """Test that non-JSON types are serialized."""
        from datetime import datetime

        response = build_response(200, {"timestamp": datetime(2024, 1, 1)})

        body = json.loads(response.body)
        assert body["timestamp"] == "2024-01-01 00:00:00"


# =============================================================================
# Success Response Tests
# =============================================================================


class TestSuccessResponse:
    """Tests for success_response function."""

    def test_default_status(self) -> None:
        """Test default 200 status code."""
        response = success_response({"id": 1})

        assert isinstance(response, Response)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["success"] is True
        assert body["data"]["id"] == 1

    def test_custom_status(self) -> None:
        """Test custom status code."""
        response = success_response({"id": 1}, status_code=201)

        assert response.status_code == 201

    def test_with_metadata(self) -> None:
        """Test including metadata."""
        response = success_response(
            {"items": []},
            meta={"total": 100, "page": 1},
        )

        body = json.loads(response.body)
        assert body["meta"]["total"] == 100
        assert body["meta"]["page"] == 1

    def test_list_data(self) -> None:
        """Test with list data."""
        response = success_response([{"id": 1}, {"id": 2}])

        body = json.loads(response.body)
        assert len(body["data"]) == 2


# =============================================================================
# Error Response Tests
# =============================================================================


class TestErrorResponse:
    """Tests for error_response function."""

    def test_basic_error(self) -> None:
        """Test basic error response."""
        response = error_response("Something went wrong")

        assert isinstance(response, Response)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["success"] is False
        assert body["error"]["message"] == "Something went wrong"

    def test_custom_status(self) -> None:
        """Test custom status code."""
        response = error_response("Not found", status_code=404)

        assert response.status_code == 404

    def test_with_error_code(self) -> None:
        """Test including error code."""
        response = error_response(
            "Invalid input",
            error_code="VALIDATION_ERROR",
        )

        body = json.loads(response.body)
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_with_details(self) -> None:
        """Test including error details."""
        response = error_response(
            "Validation failed",
            details={"field": "email", "reason": "invalid format"},
        )

        body = json.loads(response.body)
        assert body["error"]["details"]["field"] == "email"


# =============================================================================
# Created Response Tests
# =============================================================================


class TestCreatedResponse:
    """Tests for created_response function."""

    def test_status_201(self) -> None:
        """Test that status is 201."""
        response = created_response({"id": "new-123"})

        assert isinstance(response, Response)
        assert response.status_code == 201
        body = json.loads(response.body)
        assert body["success"] is True

    def test_with_location(self) -> None:
        """Test including Location header."""
        response = created_response(
            {"id": "new-123"},
            location="/v1/resources/new-123",
        )

        assert response.headers["Location"] == "/v1/resources/new-123"

    def test_without_location(self) -> None:
        """Test without Location header."""
        response = created_response({"id": "new-123"})

        assert "Location" not in response.headers


# =============================================================================
# Accepted Response Tests
# =============================================================================


class TestAcceptedResponse:
    """Tests for accepted_response function."""

    def test_status_202(self) -> None:
        """Test that status is 202."""
        response = accepted_response({"job_id": "job-123"})

        assert isinstance(response, Response)
        assert response.status_code == 202
        body = json.loads(response.body)
        assert body["success"] is True

    def test_with_location(self) -> None:
        """Test including Location header for status checking."""
        response = accepted_response(
            {"job_id": "job-123"},
            location="/v1/jobs/job-123/status",
        )

        assert response.headers["Location"] == "/v1/jobs/job-123/status"


# =============================================================================
# Not Found Response Tests
# =============================================================================


class TestNotFoundResponse:
    """Tests for not_found_response function."""

    def test_status_404(self) -> None:
        """Test that status is 404."""
        response = not_found_response("Job", "job-123")

        assert isinstance(response, Response)
        assert response.status_code == 404

    def test_message_format(self) -> None:
        """Test error message format."""
        response = not_found_response("Query", "query-456")

        body = json.loads(response.body)
        assert "Query" in body["error"]["message"]
        assert "query-456" in body["error"]["message"]

    def test_error_code(self) -> None:
        """Test error code is set."""
        response = not_found_response("Resource", "id")

        body = json.loads(response.body)
        assert body["error"]["code"] == "RESOURCE_NOT_FOUND"


# =============================================================================
# Validation Error Response Tests
# =============================================================================


class TestValidationErrorResponse:
    """Tests for validation_error_response function."""

    def test_status_422(self) -> None:
        """Test that status is 422."""
        response = validation_error_response([])

        assert isinstance(response, Response)
        assert response.status_code == 422

    def test_includes_errors(self) -> None:
        """Test that validation errors are included."""
        errors = [
            {"field": "email", "message": "Invalid email format"},
            {"field": "age", "message": "Must be positive"},
        ]

        response = validation_error_response(errors)

        body = json.loads(response.body)
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert len(body["error"]["details"]["errors"]) == 2


# =============================================================================
# Unauthorized Response Tests
# =============================================================================


class TestUnauthorizedResponse:
    """Tests for unauthorized_response function."""

    def test_status_401(self) -> None:
        """Test that status is 401."""
        response = unauthorized_response()

        assert isinstance(response, Response)
        assert response.status_code == 401

    def test_default_message(self) -> None:
        """Test default message."""
        response = unauthorized_response()

        body = json.loads(response.body)
        assert body["error"]["message"] == "Unauthorized"

    def test_custom_message(self) -> None:
        """Test custom message."""
        response = unauthorized_response("Token expired")

        body = json.loads(response.body)
        assert body["error"]["message"] == "Token expired"

    def test_error_code(self) -> None:
        """Test error code."""
        response = unauthorized_response()

        body = json.loads(response.body)
        assert body["error"]["code"] == "UNAUTHORIZED"


# =============================================================================
# Forbidden Response Tests
# =============================================================================


class TestForbiddenResponse:
    """Tests for forbidden_response function."""

    def test_status_403(self) -> None:
        """Test that status is 403."""
        response = forbidden_response()

        assert isinstance(response, Response)
        assert response.status_code == 403

    def test_default_message(self) -> None:
        """Test default message."""
        response = forbidden_response()

        body = json.loads(response.body)
        assert body["error"]["message"] == "Access denied"

    def test_custom_message(self) -> None:
        """Test custom message."""
        response = forbidden_response("Admin access required")

        body = json.loads(response.body)
        assert body["error"]["message"] == "Admin access required"

    def test_error_code(self) -> None:
        """Test error code."""
        response = forbidden_response()

        body = json.loads(response.body)
        assert body["error"]["code"] == "FORBIDDEN"


# =============================================================================
# Rate Limit Response Tests
# =============================================================================


class TestRateLimitResponse:
    """Tests for rate_limit_response function."""

    def test_status_429(self) -> None:
        """Test that status is 429."""
        response = rate_limit_response()

        assert isinstance(response, Response)
        assert response.status_code == 429

    def test_default_retry_after(self) -> None:
        """Test default retry-after value."""
        response = rate_limit_response()

        assert response.headers["Retry-After"] == "60"
        body = json.loads(response.body)
        assert body["error"]["retry_after"] == 60

    def test_custom_retry_after(self) -> None:
        """Test custom retry-after value."""
        response = rate_limit_response(retry_after=120)

        assert response.headers["Retry-After"] == "120"
        body = json.loads(response.body)
        assert body["error"]["retry_after"] == 120

    def test_error_code(self) -> None:
        """Test error code."""
        response = rate_limit_response()

        body = json.loads(response.body)
        assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"


# =============================================================================
# Internal Error Response Tests
# =============================================================================


class TestInternalErrorResponse:
    """Tests for internal_error_response function."""

    def test_status_500(self) -> None:
        """Test that status is 500."""
        response = internal_error_response()

        assert isinstance(response, Response)
        assert response.status_code == 500

    def test_default_message(self) -> None:
        """Test default message."""
        response = internal_error_response()

        body = json.loads(response.body)
        assert body["error"]["message"] == "Internal server error"

    def test_custom_message(self) -> None:
        """Test custom message."""
        response = internal_error_response("Database connection failed")

        body = json.loads(response.body)
        assert body["error"]["message"] == "Database connection failed"

    def test_with_request_id(self) -> None:
        """Test including request ID for debugging."""
        response = internal_error_response(request_id="req-abc-123")

        body = json.loads(response.body)
        assert body["error"]["details"]["request_id"] == "req-abc-123"

    def test_without_request_id(self) -> None:
        """Test without request ID."""
        response = internal_error_response()

        body = json.loads(response.body)
        assert "details" not in body["error"] or body["error"]["details"] is None

    def test_error_code(self) -> None:
        """Test error code."""
        response = internal_error_response()

        body = json.loads(response.body)
        assert body["error"]["code"] == "INTERNAL_ERROR"
