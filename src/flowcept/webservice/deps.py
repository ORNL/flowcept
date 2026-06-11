"""Dependency providers for Flowcept webservice."""

from flowcept.flowcept_api.db_api import DBAPI


def get_db_api() -> DBAPI:
    """Return the shared DB API facade."""
    return DBAPI()
