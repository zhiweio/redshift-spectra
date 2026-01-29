"""Middleware components for Redshift Spectra."""

from spectra.middleware.tenant import TenantContext, extract_tenant_context

__all__ = ["TenantContext", "extract_tenant_context"]
