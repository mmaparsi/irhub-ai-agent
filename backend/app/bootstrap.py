"""Import side effects that register agents and tools.

Both the API process and the arq worker must call this. Importing the worker
module alone does not otherwise load the tool registry, so the model would be
called with an empty tool list.
"""


def register_all() -> None:
    import app.agents.catalog  # noqa: F401
    import app.tools.builtin  # noqa: F401
