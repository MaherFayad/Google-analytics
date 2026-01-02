"""
API v1 Routes
"""

from fastapi import APIRouter

from . import (
    analytics,
    auth,
    health,
    tenants,
    unified_analytics,
    chat,
    export,
    sharing,
)
from .admin import audit_trail, tenant_management, transformation_diff

router = APIRouter()

# Core endpoints
router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])

# Analytics endpoints
router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
router.include_router(unified_analytics.router, prefix="/analytics", tags=["analytics"])

# Chat & Streaming (Task 4.2)
router.include_router(chat.router, tags=["chat"])

# Export & Sharing (Task P0-8)
router.include_router(export.router, tags=["export"])
router.include_router(sharing.router, tags=["sharing"])

# Admin endpoints
router.include_router(audit_trail.router, prefix="/admin", tags=["admin"])
router.include_router(tenant_management.router, prefix="/admin", tags=["admin"])
router.include_router(transformation_diff.router, prefix="/admin", tags=["admin"])
