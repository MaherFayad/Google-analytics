"""
Authentication middleware for FastAPI.

Implements Task P0-27: JWT Verification Middleware

This middleware intercepts all API requests and verifies JWT signatures
before allowing access to protected endpoints.
"""

import logging
from typing import Callable, Optional

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

from ..core.jwt_validator import verify_jwt_async, JWTValidationError

logger = logging.getLogger(__name__)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """
    JWT authentication middleware.
    
    Implements Task P0-27: Automatic JWT verification for all API requests
    
    Features:
    - Extracts JWT from Authorization header
    - Verifies signature using NextAuth secret
    - Attaches user info to request.state
    - Allows public endpoints (health, docs, auth)
    """
    
    # Endpoints that don't require authentication
    PUBLIC_PATHS = {
        "/",
        "/health",
        "/health/ready",
        "/health/live",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/metrics",
        "/api/v1/auth/sync",  # NextAuth sync endpoint (protected by API secret)
    }
    
    def __init__(self, app, enforce_auth: bool = True):
        """
        Initialize JWT auth middleware.
        
        Args:
            app: FastAPI application
            enforce_auth: Whether to enforce authentication (False for dev/testing)
        """
        super().__init__(app)
        self.enforce_auth = enforce_auth
        logger.info(f"JWT auth middleware initialized (enforce_auth={enforce_auth})")
    
    async def dispatch(
        self,
        request: Request,
        call_next: Callable
    ) -> Response:
        """
        Process request and verify JWT.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/endpoint
            
        Returns:
            Response from next middleware/endpoint
            
        Raises:
            HTTPException: If authentication fails
        """
        # Skip authentication for public paths
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)
        
        # Skip authentication for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Extract Authorization header
        auth_header = request.headers.get("Authorization")
        
        if not auth_header:
            if not self.enforce_auth:
                logger.debug("No auth header, but enforcement disabled")
                return await call_next(request)
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Parse Bearer token
        try:
            scheme, token = auth_header.split()
            
            if scheme.lower() != "bearer":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication scheme. Use 'Bearer'",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header format",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verify JWT signature (Task P0-27)
        try:
            payload = await verify_jwt_async(token)
            
            # Attach user info to request state
            request.state.user_id = payload.get("sub")
            request.state.email = payload.get("email")
            request.state.jwt_payload = payload
            
            logger.debug(
                f"JWT verified for user {request.state.user_id}",
                extra={"user_id": request.state.user_id, "path": request.url.path}
            )
            
        except JWTValidationError as e:
            logger.warning(f"JWT validation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid authentication token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Continue to next middleware/endpoint
        response = await call_next(request)
        return response


def get_current_user_id(request: Request) -> str:
    """
    Extract current user ID from request.
    
    Dependency for FastAPI endpoints.
    
    Args:
        request: FastAPI request (with user info from middleware)
        
    Returns:
        User ID
        
    Raises:
        HTTPException: If user not authenticated
        
    Usage:
        @app.get("/api/v1/me")
        async def get_me(user_id: str = Depends(get_current_user_id)):
            return {"user_id": user_id}
    """
    if not hasattr(request.state, "user_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated",
        )
    
    return request.state.user_id


def get_current_user_email(request: Request) -> str:
    """
    Extract current user email from request.
    
    Args:
        request: FastAPI request
        
    Returns:
        User email
    """
    if not hasattr(request.state, "email"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated",
        )
    
    return request.state.email


def get_jwt_payload(request: Request) -> dict:
    """
    Get full JWT payload from request.
    
    Args:
        request: FastAPI request
        
    Returns:
        JWT payload dict
    """
    if not hasattr(request.state, "jwt_payload"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated",
        )
    
    return request.state.jwt_payload

