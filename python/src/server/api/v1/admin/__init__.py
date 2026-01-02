"""
Admin API endpoints.

Implements Task P0-30: GDPR-Compliant Tenant Data Export & Deletion
"""

from .tenant_management import router as tenant_management_router

__all__ = ["tenant_management_router"]

