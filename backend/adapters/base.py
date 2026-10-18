"""Adapter base: the error types and the dataset shape (id, label, sourceType, layers, metadata) every adapter returns."""
from __future__ import annotations

class AdapterError(Exception):
    """Base class for adapter failures. `status` is an HTTP status hint the API
    layer turns into a response code, so failures stay clear and structured."""

    status = 500

    def __init__(self, message, *, status=None, details=None):
        super().__init__(message)
        self.message = message
        if status is not None:
            self.status = status
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": self.message, "status": self.status, "details": self.details}

class DatasetLoadError(AdapterError):
    """The source's data could not be found or read."""
    status = 404

class CompositionError(AdapterError):
    """The object was read, but what it describes cannot be used by this application."""
    status = 422

class AdapterNotImplementedError(AdapterError):
    status = 501

class DataSourceAdapter:
    adapter_name: str = "base"

    def load_dataset(self, source_config: dict, context: dict | None = None) -> dict:
        raise NotImplementedError

    @staticmethod
    def normalize_dataset(*, id, label, source_type, layers=None, metadata=None) -> dict:
        """Assemble the one stable dataset shape returned to the frontend."""
        return {
            "id": id,
            "label": label,
            "sourceType": source_type,
            "layers": layers or {},
            "metadata": metadata or {},
        }
