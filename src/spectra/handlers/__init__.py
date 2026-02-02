"""Lambda handlers for Spectra API."""

from spectra.handlers.api import handler as api_handler
from spectra.handlers.authorizer import handler as authorizer_handler
from spectra.handlers.bulk import handler as bulk_handler
from spectra.handlers.query import handler as query_handler
from spectra.handlers.result import handler as result_handler
from spectra.handlers.status import handler as status_handler
from spectra.handlers.worker import handler as worker_handler

__all__ = [
    "api_handler",
    "authorizer_handler",
    "bulk_handler",
    "query_handler",
    "result_handler",
    "status_handler",
    "worker_handler",
]
