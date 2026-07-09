"""Shared ToolResult wrapper for MCP tools and webservice chat tools."""

from typing import Union, Dict, List, Any
from pydantic import BaseModel


class ToolResult(BaseModel):
    """Standardized wrapper for tool outputs.

    Conventions
    -----------
    - 2xx: success (string result)
    - 3xx: success (dict result)
    - 4xx: error (string message)
    - 5xx: error (dict or list result)
    """

    code: int | None = None
    result: Union[str, Dict, List[Any]] = None
    extra: Dict | str | None = None
    tool_name: str | None = None

    def result_is_str(self) -> bool:
        """Return True if the result is a string."""
        return (200 <= self.code < 300) or (400 <= self.code < 500)

    def is_success(self) -> bool:
        """Return True if the result is a success."""
        return self.is_success_string() or self.is_success_dict()

    def is_success_string(self) -> bool:
        """Return True if the result is a 2xx success string."""
        return 200 <= self.code < 300

    def is_error_string(self) -> bool:
        """Return True if the result is a 4xx error string."""
        return 400 <= self.code < 500

    def is_success_dict(self) -> bool:
        """Return True if the result is a 3xx success dict."""
        return 300 <= self.code < 400
