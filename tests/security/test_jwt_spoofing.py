"""
JWT spoofing security tests.

Implements Task P0-27: Penetration tests for JWT forgery

These tests verify that the system properly rejects forged JWTs
and prevents unauthorized access to tenant data.
"""

import pytest
import time
from datetime import datetime, timedelta
from jose import jwt

from src.server.core.jwt_validator import JWTValidator, JWTValidationError
from src.server.core.config import settings


class TestJWTSpoofing:
    """Test suite for JWT spoofing prevention (Task P0-27)."""
    
    @pytest.fixture
    def validator(self):
        """Create JWT validator instance."""
        return JWTValidator()
    
    @pytest.fixture
    def valid_token(self):
        """Create a valid JWT token."""
        payload = {
            "sub": "test-user-123",
            "email": "test@example.com",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,  # 1 hour
        }
        return jwt.encode(payload, settings.NEXTAUTH_SECRET, algorithm="HS256")
    
    @pytest.fixture
    def forged_token_wrong_secret(self):
        """Create a forged token with wrong secret."""
        payload = {
            "sub": "attacker-user",
            "email": "attacker@example.com",
            "tenant_id": "victim-tenant-uuid",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        # Use wrong secret (attacker's secret)
        return jwt.encode(payload, "attacker-secret-key", algorithm="HS256")
    
    @pytest.fixture
    def expired_token(self):
        """Create an expired token."""
        payload = {
            "sub": "test-user-123",
            "email": "test@example.com",
            "iat": int(time.time()) - 7200,  # 2 hours ago
            "exp": int(time.time()) - 3600,  # Expired 1 hour ago
        }
        return jwt.encode(payload, settings.NEXTAUTH_SECRET, algorithm="HS256")
    
    @pytest.fixture
    def token_without_signature(self):
        """Create an unsigned token (None algorithm)."""
        payload = {
            "sub": "test-user-123",
            "email": "test@example.com",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        return jwt.encode(payload, None, algorithm="none")
    
    def test_valid_token_accepted(self, validator, valid_token):
        """Test that valid tokens are accepted."""
        payload = validator.verify_token(valid_token)
        
        assert payload["sub"] == "test-user-123"
        assert payload["email"] == "test@example.com"
        assert "iat" in payload
        assert "exp" in payload
    
    def test_forged_token_rejected(self, validator, forged_token_wrong_secret):
        """
        CRITICAL TEST: Forged token must be rejected.
        
        This prevents attackers from creating fake JWTs
        and accessing other tenants' data.
        """
        with pytest.raises(JWTValidationError) as exc_info:
            validator.verify_token(forged_token_wrong_secret)
        
        assert "signature" in str(exc_info.value).lower()
    
    def test_expired_token_rejected(self, validator, expired_token):
        """Test that expired tokens are rejected."""
        with pytest.raises(JWTValidationError) as exc_info:
            validator.verify_token(expired_token)
        
        assert "expired" in str(exc_info.value).lower()
    
    def test_unsigned_token_rejected(self, validator, token_without_signature):
        """Test that unsigned tokens are rejected."""
        with pytest.raises(JWTValidationError) as exc_info:
            validator.verify_token(token_without_signature)
        
        # Should fail signature verification
        assert "signature" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()
    
    def test_token_missing_required_claims(self, validator):
        """Test that tokens missing required claims are rejected."""
        # Token without 'sub' claim
        payload = {
            "email": "test@example.com",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, settings.NEXTAUTH_SECRET, algorithm="HS256")
        
        with pytest.raises(JWTValidationError) as exc_info:
            validator.verify_token(token)
        
        assert "missing" in str(exc_info.value).lower()
    
    def test_token_too_old_rejected(self, validator):
        """Test that tokens older than 24 hours are rejected."""
        payload = {
            "sub": "test-user-123",
            "email": "test@example.com",
            "iat": int(time.time()) - 90000,  # >24 hours ago
            "exp": int(time.time()) + 3600,   # But not expired yet
        }
        token = jwt.encode(payload, settings.NEXTAUTH_SECRET, algorithm="HS256")
        
        with pytest.raises(JWTValidationError) as exc_info:
            validator.verify_token(token)
        
        assert "too old" in str(exc_info.value).lower()
    
    def test_malformed_token_rejected(self, validator):
        """Test that malformed tokens are rejected."""
        malformed_tokens = [
            "not.a.jwt",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature",
            "",
            "Bearer token",
        ]
        
        for token in malformed_tokens:
            with pytest.raises(JWTValidationError):
                validator.verify_token(token)
    
    def test_extract_user_id(self, validator, valid_token):
        """Test user ID extraction from valid token."""
        user_id = validator.extract_user_id(valid_token)
        assert user_id == "test-user-123"
    
    def test_extract_email(self, validator, valid_token):
        """Test email extraction from valid token."""
        email = validator.extract_email(valid_token)
        assert email == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_middleware_integration(self, validator, valid_token):
        """Test JWT validation in middleware context."""
        # This would be tested with FastAPI TestClient
        # For now, just verify the validator works
        payload = validator.verify_token(valid_token)
        assert payload["sub"] == "test-user-123"


class TestJWTSpoofingAttackScenarios:
    """
    Advanced attack scenarios for JWT spoofing.
    
    These tests simulate real-world attacks to ensure
    the system is secure against sophisticated threats.
    """
    
    def test_tenant_spoofing_attack(self):
        """
        CRITICAL: Test that attacker cannot spoof tenant_id.
        
        Attack scenario:
        1. Attacker gets their own valid JWT
        2. Attacker modifies tenant_id in JWT
        3. Attacker signs with their own secret
        4. System must reject the forged JWT
        """
        # Attacker's valid token
        attacker_payload = {
            "sub": "attacker-123",
            "email": "attacker@evil.com",
            "tenant_id": "attacker-tenant",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        
        # Attacker modifies tenant_id
        forged_payload = attacker_payload.copy()
        forged_payload["tenant_id"] = "victim-tenant-uuid"
        
        # Attacker signs with wrong secret
        forged_token = jwt.encode(forged_payload, "attacker-secret", algorithm="HS256")
        
        # System must reject
        validator = JWTValidator()
        with pytest.raises(JWTValidationError):
            validator.verify_token(forged_token)
    
    def test_replay_attack_with_old_token(self):
        """
        Test protection against replay attacks with old tokens.
        
        Even if token was valid 25 hours ago, it should be rejected now.
        """
        old_payload = {
            "sub": "test-user",
            "email": "test@example.com",
            "iat": int(time.time()) - 90000,  # 25 hours ago
            "exp": int(time.time()) + 3600,   # Expires in future
        }
        
        old_token = jwt.encode(old_payload, settings.NEXTAUTH_SECRET, algorithm="HS256")
        
        validator = JWTValidator()
        with pytest.raises(JWTValidationError):
            validator.verify_token(old_token)
    
    def test_algorithm_confusion_attack(self):
        """
        Test protection against algorithm confusion attacks.
        
        Attacker tries to use 'none' algorithm to bypass signature.
        """
        payload = {
            "sub": "attacker",
            "email": "attacker@evil.com",
            "tenant_id": "victim-tenant",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        
        # Try to use 'none' algorithm
        none_token = jwt.encode(payload, None, algorithm="none")
        
        validator = JWTValidator()
        with pytest.raises(JWTValidationError):
            validator.verify_token(none_token)



