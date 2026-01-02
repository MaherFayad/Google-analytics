"""
Runtime schema validation middleware for agent results.

Implements Task P0-22: Agent Result Schema Registry & Validation

Features:
- Validates agent results against Pydantic schemas
- Provides detailed validation error messages
- Logs validation failures for debugging
- Supports type coercion and strict mode

Usage:
    from agents.middleware.schema_validator import validate_agent_result
    from agents.schemas.results import DataFetchResult
    
    # Validate result
    validated_result = validate_agent_result(
        result_data,
        DataFetchResult,
        agent_name="DataFetcherAgent"
    )
"""

import logging
from typing import Any, Dict, Type, TypeVar
from pydantic import BaseModel, ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


class ValidationError(Exception):
    """Custom validation error with detailed context."""
    
    def __init__(
        self,
        agent_name: str,
        schema_name: str,
        errors: list,
        original_data: Dict[str, Any]
    ):
        self.agent_name = agent_name
        self.schema_name = schema_name
        self.errors = errors
        self.original_data = original_data
        
        # Format error message
        error_details = "\n".join([
            f"  - {err['loc']}: {err['msg']}"
            for err in errors
        ])
        
        message = (
            f"Schema validation failed for {agent_name} → {schema_name}:\n"
            f"{error_details}"
        )
        
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging/serialization."""
        return {
            "agent_name": self.agent_name,
            "schema_name": self.schema_name,
            "errors": self.errors,
            "original_data_keys": list(self.original_data.keys())
        }


class SchemaValidator:
    """
    Runtime schema validator for agent results.
    
    Validates agent outputs against Pydantic V2 schemas with
    comprehensive error handling and logging.
    
    Features:
    - Type validation
    - Field presence checking
    - Custom validator execution
    - Detailed error reporting
    - Performance monitoring
    """
    
    def __init__(self, strict: bool = True):
        """
        Initialize schema validator.
        
        Args:
            strict: If True, raise ValidationError on failure.
                   If False, log warnings and return None.
        """
        self.strict = strict
        self._validation_counts = {
            "success": 0,
            "failure": 0
        }
    
    def validate(
        self,
        data: Dict[str, Any],
        schema: Type[T],
        agent_name: str,
        context: Dict[str, Any] = None
    ) -> T:
        """
        Validate data against schema.
        
        Args:
            data: Raw data to validate
            schema: Pydantic model class
            agent_name: Name of agent producing the result
            context: Additional context for logging
        
        Returns:
            Validated Pydantic model instance
        
        Raises:
            ValidationError: If validation fails and strict=True
        """
        try:
            # Validate with Pydantic
            validated = schema(**data)
            
            # Track success
            self._validation_counts["success"] += 1
            
            logger.debug(
                f"Schema validation passed: {agent_name} → {schema.__name__}",
                extra={
                    "agent_name": agent_name,
                    "schema_name": schema.__name__,
                    "context": context or {}
                }
            )
            
            return validated
        
        except PydanticValidationError as e:
            # Track failure
            self._validation_counts["failure"] += 1
            
            # Format validation errors
            errors = e.errors()
            
            logger.error(
                f"Schema validation failed: {agent_name} → {schema.__name__}",
                extra={
                    "agent_name": agent_name,
                    "schema_name": schema.__name__,
                    "errors": errors,
                    "data_keys": list(data.keys()),
                    "context": context or {}
                },
                exc_info=True
            )
            
            if self.strict:
                raise ValidationError(
                    agent_name=agent_name,
                    schema_name=schema.__name__,
                    errors=errors,
                    original_data=data
                )
            else:
                # Non-strict mode: log and return None
                logger.warning(
                    f"Validation failed but continuing (strict=False): "
                    f"{agent_name} → {schema.__name__}"
                )
                return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get validation statistics."""
        total = self._validation_counts["success"] + self._validation_counts["failure"]
        success_rate = (
            self._validation_counts["success"] / total * 100
            if total > 0
            else 0
        )
        
        return {
            "total_validations": total,
            "success_count": self._validation_counts["success"],
            "failure_count": self._validation_counts["failure"],
            "success_rate_percent": round(success_rate, 2)
        }


# Global validator instance
_global_validator: SchemaValidator = None


def get_validator(strict: bool = True) -> SchemaValidator:
    """
    Get or create global validator instance.
    
    Args:
        strict: Strict validation mode
    
    Returns:
        SchemaValidator instance
    """
    global _global_validator
    
    if _global_validator is None:
        _global_validator = SchemaValidator(strict=strict)
    
    return _global_validator


def validate_agent_result(
    data: Dict[str, Any],
    schema: Type[T],
    agent_name: str,
    strict: bool = True,
    context: Dict[str, Any] = None
) -> T:
    """
    Convenience function to validate agent result.
    
    Args:
        data: Raw data to validate
        schema: Pydantic model class
        agent_name: Name of agent producing the result
        strict: If True, raise on validation error
        context: Additional context for logging
    
    Returns:
        Validated Pydantic model instance
    
    Raises:
        ValidationError: If validation fails and strict=True
    
    Example:
        from agents.schemas.results import DataFetchResult
        
        result_data = {
            "status": "success",
            "data": {...},
            "tenant_id": "...",
            ...
        }
        
        validated = validate_agent_result(
            result_data,
            DataFetchResult,
            agent_name="DataFetcherAgent"
        )
    """
    validator = get_validator(strict=strict)
    return validator.validate(data, schema, agent_name, context)


def reset_validator():
    """Reset global validator (for testing)."""
    global _global_validator
    _global_validator = None

