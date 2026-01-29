"""API response utilities for Lambda handlers."""

import json
from typing import Any


def build_response(
    status_code: int,
    body: dict[str, Any] | list[Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a standard API Gateway response.

    Args:
        status_code: HTTP status code
        body: Response body (will be JSON serialized)
        headers: Additional headers to include

    Returns:
        API Gateway compatible response dictionary
    """
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Tenant-ID,X-Request-ID",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    }

    if headers:
        default_headers.update(headers)

    response: dict[str, Any] = {
        "statusCode": status_code,
        "headers": default_headers,
    }

    if body is not None:
        response["body"] = json.dumps(body, default=str)
    else:
        response["body"] = ""

    return response


def success_response(
    data: dict[str, Any] | list[Any],
    status_code: int = 200,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a success response.

    Args:
        data: Response data
        status_code: HTTP status code (default 200)
        meta: Optional metadata

    Returns:
        API Gateway compatible response
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
) -> dict[str, Any]:
    """Build an error response.

    Args:
        message: Error message
        status_code: HTTP status code
        error_code: Optional error code for programmatic handling
        details: Optional error details

    Returns:
        API Gateway compatible error response
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
) -> dict[str, Any]:
    """Build a 201 Created response.

    Args:
        data: Created resource data
        location: Optional Location header value

    Returns:
        API Gateway compatible response
    """
    headers = {"Location": location} if location else None
    return build_response(201, {"success": True, "data": data}, headers)


def accepted_response(
    data: dict[str, Any],
    location: str | None = None,
) -> dict[str, Any]:
    """Build a 202 Accepted response for async operations.

    Args:
        data: Response data (typically job info)
        location: Optional location to check status

    Returns:
        API Gateway compatible response
    """
    headers = {"Location": location} if location else None
    return build_response(202, {"success": True, "data": data}, headers)


def not_found_response(resource: str, resource_id: str) -> dict[str, Any]:
    """Build a 404 Not Found response.

    Args:
        resource: Resource type (e.g., "Job", "Query")
        resource_id: Resource identifier

    Returns:
        API Gateway compatible error response
    """
    return error_response(
        message=f"{resource} with ID '{resource_id}' not found",
        status_code=404,
        error_code="RESOURCE_NOT_FOUND",
    )


def validation_error_response(errors: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a 422 Validation Error response.

    Args:
        errors: List of validation errors

    Returns:
        API Gateway compatible error response
    """
    return error_response(
        message="Validation failed",
        status_code=422,
        error_code="VALIDATION_ERROR",
        details={"errors": errors},
    )


def unauthorized_response(message: str = "Unauthorized") -> dict[str, Any]:
    """Build a 401 Unauthorized response.

    Args:
        message: Error message

    Returns:
        API Gateway compatible error response
    """
    return error_response(
        message=message,
        status_code=401,
        error_code="UNAUTHORIZED",
    )


def forbidden_response(message: str = "Access denied") -> dict[str, Any]:
    """Build a 403 Forbidden response.

    Args:
        message: Error message

    Returns:
        API Gateway compatible error response
    """
    return error_response(
        message=message,
        status_code=403,
        error_code="FORBIDDEN",
    )


def rate_limit_response(retry_after: int = 60) -> dict[str, Any]:
    """Build a 429 Too Many Requests response.

    Args:
        retry_after: Seconds to wait before retrying

    Returns:
        API Gateway compatible error response
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
) -> dict[str, Any]:
    """Build a 500 Internal Server Error response.

    Args:
        message: Error message
        request_id: Optional request ID for debugging

    Returns:
        API Gateway compatible error response
    """
    details = {"request_id": request_id} if request_id else None
    return error_response(
        message=message,
        status_code=500,
        error_code="INTERNAL_ERROR",
        details=details,
    )
