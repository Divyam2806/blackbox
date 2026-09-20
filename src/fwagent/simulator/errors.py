"""
Simulator Exception Types for fwagent.
"""


class BackendUnavailable(RuntimeError):
    """Raised when a backend was explicitly required but cannot run."""
