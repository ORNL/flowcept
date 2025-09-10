CLI Reference
=============

.. toctree::
   :maxdepth: 2
   :caption: Contents:

Flowcept's CLI is available immediatelly after you run `pip install flowcept`.

.. code-block:: shell

   flowcept --help

Shows all available commands with their helper description and arguments.


Usage pattern
-------------

.. code-block:: shell

   flowcept --<function-name-with-dashes> [--<arg-name-with-dashes>=<value>] ...

Rules:
- Commands come from :mod:`flowcept.cli` public functions.
- Underscores become hyphens (e.g., ``stream_messages`` → ``--stream-messages``).
- Bool params work as flags (present/absent). Other params require a value.

Available commands
------------------

.. automodule:: flowcept.cli
   :members:
   :member-order: bysource
   :undoc-members:
   :exclude-members: main, no_docstring, COMMAND_GROUPS, COMMANDS
