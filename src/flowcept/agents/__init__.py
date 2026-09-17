# flake8: noqa: F403
"""Agents subpackage.

Exports are resolved lazily (PEP 562). The MCP tool modules pull in optional
heavy dependencies (mcp, pandas, ...), and this package is also on the import
path of the harness capture hooks, which run as short-lived processes on an
interactive critical path and must stay stdlib-cheap. Importing
``flowcept.agents`` therefore imports nothing until an attribute is accessed.
"""

_LAZY_MODULES = (
    "flowcept.agents.tool_result",
    "flowcept.agents.mcp.mcp_tools",
    "flowcept.agents.mcp.mcp_tools.df_query_mcp_tools",
    "flowcept.agents.mcp.mcp_tools.db_query_mcp_tools",
)


def __getattr__(name):
    import importlib

    for _mod_name in _LAZY_MODULES:
        try:
            _mod = importlib.import_module(_mod_name)
        except Exception:
            continue
        if hasattr(_mod, name):
            return getattr(_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
