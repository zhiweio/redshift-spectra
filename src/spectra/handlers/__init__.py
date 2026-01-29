"""Lambda handlers for Spectra API."""

from spectra.handlers.bulk import handler as bulk_handler
from spectra.handlers.query import handler as query_handler
from spectra.handlers.result import handler as result_handler
from spectra.handlers.status import handler as status_handler

__all__ = [
    "bulk_handler",
    "query_handler",
    "result_handler",
    "status_handler",
]
