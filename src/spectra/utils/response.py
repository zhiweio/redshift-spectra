"""API response utilities for Lambda handlers.

This module provides helper functions to build aws_lambda_powertools Response objects
for use with APIGatewayRestResolver.
"""

import json
from typing import Any

from aws_lambda_powertools.event_handler import Response


def api_response(
    status_code: int,
    body: dict[str, Any] | list[Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    """Build a Response object with standard headers.

    Args:
        status_code: HTTP status code
        body: Response body (will be JSON serialized)
        headers: Additional headers to include

    Returns:
        aws_lambda_powertools Response object
    """
    return build_response(status_code, body, headers)


def build_response(
    status_code: int,
    body: dict[str, Any] | list[Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    """Build a standard Response object.

    Args:
        status_code: HTTP status code
        body: Response body (will be JSON serialized)
        headers: Additional headers to include

    Returns:
        aws_lambda_powertools Response object
    """
    response_headers: dict[str, str] = {}
    if headers:
        response_headers.update(headers)

    body_str = json.dumps(body, default=str) if body is not None else ""

    return Response(
        status_code=status_code,
        content_type="application/json",
        body=body_str,
        headers=response_headers if response_headers else None,
    )


def success_response(
    data: dict[str, Any] | list[Any],
    status_code: int = 200,
    meta: dict[str, Any] | None = None,
) -> Response:
    """Build a success response.

    Args:
        data: Response data
        status_code: HTTP status code (default 200)
        meta: Optional metadata

    Returns:
        aws_lambda_powertools Response object
    """
    body: dict[str, Any] = {"success": True, "data": data}
    if meta:
        body["meta"] = meta
    return build_response(status_code, body)


def error_response(
    message: str,
    status_code: int = 400,
    error_code: str | None = None,
    details: dict[str, Any] | None = None,
) -> Response:
    """Build an error response.

    Args:
        message: Error message
        status_code: HTTP status code
        error_code: Optional error code for programmatic handling
        details: Optional error details

    Returns:
        aws_lambda_powertools Response object
    """
    body: dict[str, Any] = {
        "success": False,
        "error": {
            "message": message,
        },
    }

    if error_code:
        body["error"]["code"] = error_code

    if details:
        body["error"]["details"] = details

    return build_response(status_code, body)


def created_response(
    data: dict[str, Any],
    location: str | None = None,
) -> Response:
    """Build a 201 Created response.

    Args:
        data: Created resource data
        location: Optional Location header value

    Returns:
        aws_lambda_powertools Response object
    """
    headers = {"Location": location} if location else None
    return build_response(201, {"success": True, "data": data}, headers)


def accepted_response(
    data: dict[str, Any],
    location: str | None = None,
) -> Response:
    """Build a 202 Accepted response for async operations.

    Args:
        data: Response data (typically job info)
        location: Optional location to check status

    Returns:
        aws_lambda_powertools Response object
    """
    headers = {"Location": location} if location else None
    return build_response(202, {"success": True, "data": data}, headers)


def not_found_response(resource: str, resource_id: str) -> Response:
    """Build a 404 Not Found response.

    Args:
        resource: Resource type (e.g., "Job", "Query")
        resource_id: Resource identifier

    Returns:
        aws_lambda_powertools Response object
    """
    return error_response(
        message=f"{resource} with ID '{resource_id}' not found",
        status_code=404,
        error_code="RESOURCE_NOT_FOUND",
    )


def validation_error_response(errors: list[dict[str, Any]]) -> Response:
    """Build a 422 Validation Error response.

    Args:
        errors: List of validation errors

    Returns:
        aws_lambda_powertools Response object
    """
    return error_response(
        message="Validation failed",
        status_code=422,
        error_code="VALIDATION_ERROR",
        details={"errors": errors},
    )


def unauthorized_response(message: str = "Unauthorized") -> Response:
    """Build a 401 Unauthorized response.

    Args:
        message: Error message

    Returns:
        aws_lambda_powertools Response object
    """
    return error_response(
        message=message,
        status_code=401,
        error_code="UNAUTHORIZED",
    )


def forbidden_response(message: str = "Access denied") -> Response:
    """Build a 403 Forbidden response.

    Args:
        message: Error message

    Returns:
        aws_lambda_powertools Response object
    """
    return error_response(
        message=message,
        status_code=403,
        error_code="FORBIDDEN",
    )


def rate_limit_response(retry_after: int = 60) -> Response:
    """Build a 429 Too Many Requests response.

    Args:
        retry_after: Seconds to wait before retrying

    Returns:
        aws_lambda_powertools Response object
    """
    return build_response(
        429,
        {
            "success": False,
            "error": {
                "message": "Rate limit exceeded",
                "code": "RATE_LIMIT_EXCEEDED",
                "retry_after": retry_after,
            },
        },
        {"Retry-After": str(retry_after)},
    )


def internal_error_response(
    message: str = "Internal server error",
    request_id: str | None = None,
) -> Response:
    """Build a 500 Internal Server Error response.

    Args:
        message: Error message
        request_id: Optional request ID for debugging

    Returns:
        aws_lambda_powertools Response object
    """
    details = {"request_id": request_id} if request_id else None
    return error_response(
        message=message,
        status_code=500,
        error_code="INTERNAL_ERROR",
        details=details,
    )
