"""
Custom Exceptions

Application-specific exceptions for error handling.
"""


class MeridianException(Exception):
    """Base exception for all MERIDIAN errors."""

    def __init__(self, message: str, code: str = "MERIDIAN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class ConfigurationError(MeridianException):
    """Raised when configuration is invalid."""

    def __init__(self, message: str):
        super().__init__(message, "CONFIG_ERROR")


class DatabaseError(MeridianException):
    """Raised when database operations fail."""

    def __init__(self, message: str):
        super().__init__(message, "DATABASE_ERROR")


class QueryValidationError(MeridianException):
    """Raised when query validation fails."""

    def __init__(self, message: str):
        super().__init__(message, "QUERY_VALIDATION_ERROR")


class AgentError(MeridianException):
    """Raised when agent execution fails."""

    def __init__(self, message: str):
        super().__init__(message, "AGENT_ERROR")


class ToolExecutionError(MeridianException):
    """Raised when tool execution fails."""

    def __init__(self, message: str):
        super().__init__(message, "TOOL_EXECUTION_ERROR")


class ViewRegistryError(MeridianException):
    """Raised when view registry operations fail."""

    def __init__(self, message: str):
        super().__init__(message, "VIEW_REGISTRY_ERROR")


class AuthenticationError(MeridianException):
    """Raised when authentication fails (invalid/missing credentials)."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, "AUTHENTICATION_ERROR")


class AuthorizationError(MeridianException):
    """Raised when a user lacks permission for a resource."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, "AUTHORIZATION_ERROR")
