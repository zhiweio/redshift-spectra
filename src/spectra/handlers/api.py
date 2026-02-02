"""Unified API Lambda handler.

This handler consolidates all API routes into a single Lambda function
for simplified deployment and routing through API Gateway.
"""

from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext

from spectra.handlers.bulk import app as bulk_app

# Import route handlers from individual modules
from spectra.handlers.query import app as query_app
from spectra.handlers.result import app as result_app
from spectra.handlers.status import app as status_app
from spectra.utils.response import api_response

logger = Logger()
tracer = Tracer()
metrics = Metrics()

# Create unified app instance
app = APIGatewayRestResolver()


# =============================================================================
# Health Check Endpoint
# =============================================================================


@app.get("/health")
@tracer.capture_method
def health_check() -> Response:
    """Health check endpoint for load balancer.

    Returns:
        Health status response
    """
    return api_response(
        200,
        {
            "status": "healthy",
            "service": "redshift-spectra",
        },
    )


@app.get("/")
@tracer.capture_method
def root() -> Response:
    """Root endpoint with API information.

    Returns:
        API information response
    """
    return api_response(
        200,
        {
            "service": "redshift-spectra",
            "version": "1.0.0",
            "endpoints": {
                "health": "/health",
                "queries": "/v1/queries",
                "bulk_jobs": "/v1/bulk/jobs",
                "jobs": "/v1/jobs/{job_id}",
                "results": "/v1/jobs/{job_id}/results",
            },
        },
    )


# =============================================================================
# Lambda Handler
# =============================================================================


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Unified Lambda handler for all API requests.

    Routes requests to appropriate sub-handlers based on path.
    """
    path = event.get("path", "")
    http_method = event.get("httpMethod", "GET")

    logger.info(f"Received request: {http_method} {path}")

    # Route to appropriate handler based on path prefix
    if path.startswith("/v1/queries"):
        return query_app.resolve(event, context)
    elif path.startswith("/v1/bulk"):
        return bulk_app.resolve(event, context)
    elif path.startswith("/v1/jobs") and "/results" in path:
        return result_app.resolve(event, context)
    elif path.startswith("/v1/jobs"):
        return status_app.resolve(event, context)
    else:
        # Handle health check and root endpoints locally
        return app.resolve(event, context)
