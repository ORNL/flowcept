"""Schema introspection utility for building prompt context from class attribute docstrings.

Called once at MCP server startup. Never imported by producer-path code.
"""

import ast
import inspect
import textwrap
from typing import Any


class SchemaDocumentationError(Exception):
    """Raised at MCP server startup when a domain class has undocumented fields."""


def get_attribute_docstrings(cls: type) -> dict[str, str]:
    """Extract attribute docstrings from a class via AST parsing.

    Reads the source of ``cls`` and walks its class body looking for annotated
    assignments (``AnnAssign``) immediately followed by a string literal
    (``Expr(Constant(str))``), which is the Python attribute-docstring convention.

    Parameters
    ----------
    cls : type
        The class to introspect.

    Returns
    -------
    dict[str, str]
        Mapping of field name to its docstring. Fields without a following
        string literal are not included.
    """
    try:
        source = textwrap.dedent(inspect.getsource(cls))
        tree = ast.parse(source)
    except (OSError, TypeError, IndentationError):
        return {}

    class_def = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == cls.__name__),
        None,
    )
    if class_def is None:
        return {}

    docs: dict[str, str] = {}
    body = class_def.body
    for i, node in enumerate(body):
        if not (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)):
            continue
        if i + 1 >= len(body):
            continue
        next_node = body[i + 1]
        if (
            isinstance(next_node, ast.Expr)
            and isinstance(next_node.value, ast.Constant)
            and isinstance(next_node.value.value, str)
        ):
            docs[node.target.id] = next_node.value.value.strip()
    return docs


def assert_schema_documented(*classes: type) -> None:
    """Assert every non-private annotated field on each class has an attribute docstring.

    Called at MCP server startup. Raises ``SchemaDocumentationError`` loudly so
    the server refuses to start when any field is undocumented. Treat a startup
    failure here as a bug: add the missing attribute docstring to the class.

    Parameters
    ----------
    *classes : type
        Domain classes to check (e.g. TaskObject, TelemetrySummary).

    Raises
    ------
    SchemaDocumentationError
        If any class has fields without attribute docstrings.
    """
    errors: list[str] = []
    for cls in classes:
        annotations = {
            name: hint for name, hint in getattr(cls, "__annotations__", {}).items() if not name.startswith("_")
        }
        if not annotations:
            continue
        docs = get_attribute_docstrings(cls)
        missing = [name for name in annotations if name not in docs]
        if missing:
            errors.append(f"  {cls.__qualname__}: {missing}")

    if errors:
        raise SchemaDocumentationError(
            "MCP server cannot start — the following fields are missing attribute docstrings.\n"
            "Add a triple-quoted string immediately after each field declaration:\n\n"
            + "\n".join(errors)
            + "\n\nExample:\n"
            "    my_field: str = None\n"
            '    """Description of my_field."""\n'
        )


def _build_field_table(cls: type, subclasses: dict[str, type] | None = None) -> list[dict[str, Any]]:
    """Build a list of field descriptors for a class, expanding known subclasses.

    Parameters
    ----------
    cls : type
        The class to describe.
    subclasses : dict[str, type], optional
        Mapping of field name to its nested class, used to expand composite fields
        (e.g. ``{"cpu": CpuSummary}``).

    Returns
    -------
    list[dict]
        Each entry has ``name``, ``type``, and ``description``. Nested fields
        use dot-notation names (e.g. ``cpu.percent_all_diff``).
    """
    docs = get_attribute_docstrings(cls)
    annotations = {name: hint for name, hint in getattr(cls, "__annotations__", {}).items() if not name.startswith("_")}
    rows: list[dict[str, Any]] = []
    for name, hint in annotations.items():
        doc = docs.get(name, "")
        type_str = getattr(hint, "__name__", str(hint))
        if subclasses and name in subclasses:
            sub_cls = subclasses[name]
            sub_docs = get_attribute_docstrings(sub_cls)
            sub_annotations = {
                n: h for n, h in getattr(sub_cls, "__annotations__", {}).items() if not n.startswith("_")
            }
            for sub_name, sub_hint in sub_annotations.items():
                rows.append(
                    {
                        "name": f"{name}.{sub_name}",
                        "type": getattr(sub_hint, "__name__", str(sub_hint)),
                        "description": sub_docs.get(sub_name, ""),
                    }
                )
        else:
            rows.append({"name": name, "type": type_str, "description": doc})
    return rows


def build_schema_context() -> dict[str, list[dict[str, Any]]]:
    """Build the full static schema context at MCP server startup.

    Introspects domain classes to produce field tables used by prompt builders.
    The result is cached as ``SCHEMA_CONTEXT`` at module level — call this once.

    Returns
    -------
    dict
        Keys: ``task_fields``, ``workflow_fields``, ``agent_fields``,
        ``blob_fields``, ``telemetry_summary_fields``.
        Each value is a list of ``{name, type, description}`` dicts.
    """
    from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
    from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject
    from flowcept.commons.flowcept_dataclasses.agent_object import AgentObject
    from flowcept.commons.flowcept_dataclasses.blob_object import BlobObject
    from flowcept.commons.task_data_preprocess import (
        TelemetrySummary,
        CpuSummary,
        MemorySummary,
        DiskSummary,
        NetworkSummary,
    )

    telemetry_subclasses = {
        "cpu": CpuSummary,
        "memory": MemorySummary,
        "disk": DiskSummary,
        "network": NetworkSummary,
    }

    return {
        "task_fields": _build_field_table(TaskObject),
        "workflow_fields": _build_field_table(WorkflowObject),
        "agent_fields": _build_field_table(AgentObject),
        "blob_fields": _build_field_table(BlobObject),
        "telemetry_summary_fields": _build_field_table(TelemetrySummary, subclasses=telemetry_subclasses),
    }


# Populated at MCP server startup via mcp_server.py lifespan.
# Do not access before assert_schema_documented() has been called.
SCHEMA_CONTEXT: dict[str, list[dict[str, Any]]] = {}
