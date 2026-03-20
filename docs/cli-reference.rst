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

Configuration Profiles
----------------------

Flowcept provides quick settings profiles to switch between common runtime modes:

.. code-block:: shell

   flowcept --config-profile full-online
   flowcept --config-profile mq-only
   flowcept --config-profile full-offline

Behavior:
- Prints the exact settings keys that will change and their new values.
- Prompts for confirmation before writing changes.
- Writes to ``FLOWCEPT_SETTINGS_PATH`` when set; otherwise writes to ``~/.flowcept/settings.yaml``.

Use ``-y`` (or ``--yes``) to skip the confirmation prompt:

.. code-block:: shell

   flowcept --config-profile full-online -y

Current profile values:

- ``full-online``:
  - ``project.db_flush_mode: online``
  - ``mq.enabled: true``
  - ``kv_db.enabled: true``
  - ``databases.mongodb.enabled: true``
  - ``databases.lmdb.enabled: false``
- ``mq-only``:
  - ``project.db_flush_mode: online``
  - ``mq.enabled: true``
  - ``kv_db.enabled: false``
  - ``databases.mongodb.enabled: false``
  - ``databases.lmdb.enabled: false``
  - Use ``Flowcept(check_safe_stops=False)`` with this profile.
- ``full-offline``:
  - ``project.db_flush_mode: offline``
  - ``project.dump_buffer.enabled: true``
  - ``mq.enabled: false``
  - ``kv_db.enabled: false``
  - ``databases.mongodb.enabled: false``
  - ``databases.lmdb.enabled: false``

Available commands
------------------

.. automodule:: flowcept.cli
   :members:
   :member-order: bysource
   :undoc-members:
   :exclude-members: main, no_docstring, COMMAND_GROUPS, COMMANDS
