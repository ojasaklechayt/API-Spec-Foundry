"""Domain exceptions for the Foundry MCP runtime."""


class DraftSpecError(Exception):
    """Raised when spec drafting fails."""


class SpecValidationError(Exception):
    """Raised when spec validation fails."""


class GenerationError(Exception):
    """Raised when code generation fails."""


class UnsafeOutputPathError(GenerationError):
    """Raised when a requested output path is unsafe to write to."""
