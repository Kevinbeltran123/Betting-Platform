"""Custom exceptions for the betting intelligence platform."""


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""


class StorageError(Exception):
    """Raised when storage layer operations fail."""


class DataValidationError(Exception):
    """Raised when data validation fails."""


class ApiError(Exception):
    """Raised when an external API call fails after all retries."""


class SchedulerError(Exception):
    """Raised when APScheduler job registration or execution fails."""


class ClvError(Exception):
    """Raised when CLV calculation or recording fails."""
