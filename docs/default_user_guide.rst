Default Developer Guide
=======================

Start here for a practical end-to-end Flowcept path.

- Repository guide (full markdown):
  `docs/README.md <https://github.com/ORNL/flowcept/blob/main/docs/README.md>`_
- ReadTheDocs sections used by that guide:

  - :doc:`setup`
  - :doc:`prov_capture`
  - :doc:`prov_query`
  - :doc:`rest_api`
  - :doc:`reporting`
  - :doc:`agent`
  - :doc:`telemetry_capture`
  - :doc:`architecture`

What this guide covers
----------------------

- installation and settings as the single source of truth
- capture APIs from simplest to advanced (loops, torch, adapters, agents)
- querying via Python API, REST API, MQ consumers, and offline files
- agentic interaction with external or internal LLM modes
- provenance cards (markdown) and full PDF provenance reports
- architecture links for deeper internals

For software developers, this is the recommended first read before drilling into detailed pages.

Quick profile switch
--------------------

Use CLI profiles to switch between common runtime settings quickly:

.. code-block:: shell

   flowcept --init-settings --full
   flowcept --config-profile full-online
   flowcept --config-profile full-telemetry
   flowcept --config-profile mq-only
   flowcept --config-profile full-offline
   flowcept --config-profile mq-only-no-flush

The CLI prints exactly which keys will change, asks for confirmation, and writes to
``FLOWCEPT_SETTINGS_PATH`` (if set) or ``~/.flowcept/settings.yaml``.

Short rule:

- ``--init-settings`` creates a file
- ``--config-profile`` changes its mode
- adapter flags add adapter sections to the current file

See :doc:`cli-reference` for full details.
