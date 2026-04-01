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
   flowcept --config-profile full-telemetry
   flowcept --config-profile mq-only
   flowcept --config-profile full-offline

Settings bootstrap
------------------

Use ``--init-settings`` to create a file, then optionally apply a profile:

.. code-block:: shell

   flowcept --init-settings
   flowcept --init-settings --full
   flowcept --config-profile full-online

Meaning:

- ``flowcept --init-settings``: create a minimal file from ``DEFAULT_SETTINGS``.
- ``flowcept --init-settings --full``: copy ``resources/sample_settings.yaml``.
- ``flowcept --config-profile ...``: modify the existing file in place.

Adapter flags are additive:

.. code-block:: shell

   flowcept --init-settings --dask -y
   flowcept --init-settings --mlflow -y
   flowcept --init-settings --tensorboard -y

They add ``adapters.<name>`` to the current settings file instead of replacing it.

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
  - ``db_buffer.insertion_buffer_time_secs: 5``
- ``full-telemetry``:
  - enables CPU, per-CPU, process, memory, disk, network, and machine telemetry
  - ``telemetry_capture.gpu: null``
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

Environment variables can override settings values at runtime. This matters for keys such as
``MONGO_ENABLED``, ``LMDB_ENABLED``, ``MQ_ENABLED``, ``MQ_TYPE``, ``MQ_PORT``, and ``DB_FLUSH_MODE``.

Available commands
------------------

.. automodule:: flowcept.cli
   :members:
   :member-order: bysource
   :undoc-members:
   :exclude-members: main, no_docstring, COMMAND_GROUPS, COMMANDS
