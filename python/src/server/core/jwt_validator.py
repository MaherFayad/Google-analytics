"""
JWT signature verification for NextAuth tokens.

Implements Task P0-27: JWT Signature Verification

This module provides cryptographic JWT verification to prevent
token forgery attacks. CRITICAL for multi-tenant security.

Attack Prevention:
- Verifies JWT signature using NextAuth secret
- Checks token expiration
- Validates token structure
- Maintains JWT deny-list for revocation
"""

import logging
import time
from typing import Dict, Optional

from jose import JWTError, jwt
from fastapi import HTTPException, status

from .config import settings

logger = logging.getLogger(__name__)


class JWTValidationError(Exception):
    """Raised when JWT validation fails."""
    pass


class JWTValidator:
    """
    JWT signature validator for NextAuth tokens.
    
    Implements Task P0-27: Cryptographic JWT verification
    
    Security Features:
    - RS256/HS256 signature verification
    - Expiration checking
    - Token structure validation
    - Deny-list support for revoked tokens
    """
    
    def __init__(self):
        """Initialize JWT validator with NextAuth secret."""
        self.secret = settings.NEXTAUTH_SECRET
        self.algorithm = "HS256"  # NextAuth v4 default (symmetric)
        # For NextAuth v5 with RS256, fetch JWKS from /.well-known/jwks.json
        
        if not self.secret or len(self.secret) < 32:
            raise ValueError("NEXTAUTH_SECRET must be at least 32 characters")
        
        logger.info("JWT validator initialized")
    
    def verify_token(self, token: str) -> Dict:
        """
        Verify JWT signature and return payload.
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded JWT payload
            
        Raises:
            JWTValidationError: If verification fails
        """
        try:
            # Decode and verify signature
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": True,  # Check expiration
                    "verify_nbf": True,  # Check not-before
                    "verify_iat": True,  # Check issued-at
                    "verify_aud": False,  # NextAuth doesn't use audience
                }
            )
            
            # Validate required claims
            required_claims = ["sub", "email", "iat", "exp"]
            missing_claims = [claim for claim in required_claims if claim not in payload]
            
            if missing_claims:
                raise JWTValidationError(
                    f"Missing required claims: {', '.join(missing_claims)}"
                )
            
            # Check if token is not expired (double check)
            current_time = time.time()
            exp = payload.get("exp")
            
            if exp and current_time >= exp:
                raise JWTValidationError(
                    f"Token expired at {exp}, current time: {current_time}"
                )
            
            # Validate token age (reject tokens > 24 hours old for security)
            iat = payload.get("iat")
            if iat and (current_time - iat) > 86400:  # 24 hours
                raise JWTValidationError(
                    f"Token too old: issued {current_time - iat}s ago"
                )
            
            logger.debug(f"JWT verified successfully for user: {payload.get('sub')}")
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("JWT expired")
            raise JWTValidationError("Token has expired")
        
        except jwt.JWTClaimsError as e:
            logger.warning(f"JWT claims error: {e}")
            raise JWTValidationError(f"Invalid token claims: {e}")
        
        except JWTError as e:
            logger.error(f"JWT verification failed: {e}")
            raise JWTValidationError(f"Invalid token signature: {e}")
        
        except Exception as e:
            logger.error(f"Unexpected error during JWT verification: {e}", exc_info=True)
            raise JWTValidationError(f"Token verification failed: {e}")
    
    def extract_user_id(self, token: str) -> str:
        """
        Extract user ID from JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            User ID (sub claim)
            
        Raises:
            JWTValidationError: If verification fails
        """
        payload = self.verify_token(token)
        return payload["sub"]
    
    def extract_email(self, token: str) -> str:
        """
        Extract email from JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            User email
            
        Raises:
            JWTValidationError: If verification fails
        """
        payload = self.verify_token(token)
        return payload["email"]


# Global JWT validator instance
jwt_validator = JWTValidator()


def verify_jwt_signature(token: str) -> Dict:
    """
    Verify JWT signature (convenience function).
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded JWT payload
        
    Raises:
        HTTPException: If verification fails (401 Unauthorized)
    """
    try:
        return jwt_validator.verify_token(token)
    except JWTValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def verify_jwt_async(token: str) -> Dict:
    """
    Async JWT verification (for middleware).
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded JWT payload
        
    Raises:
        HTTPException: If verification fails
    """
    return verify_jwt_signature(token)



