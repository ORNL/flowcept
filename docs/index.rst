Flowcept
========

.. raw:: html

   <style>
     /* Show/hide logos based on Furo's theme attribute */
     .logo-light { display: inline; }
     .logo-dark  { display: none; }

     html[data-theme="dark"] .logo-light { display: none; }
     html[data-theme="dark"] .logo-dark  { display: inline; }

     /* When Furo is in 'auto', follow the OS preference */
     html[data-theme="auto"] .logo-light { display: inline; }
     html[data-theme="auto"] .logo-dark  { display: none; }
     @media (prefers-color-scheme: dark) {
       html[data-theme="auto"] .logo-light { display: none; }
       html[data-theme="auto"] .logo-dark  { display: inline; }
     }

     .hero { text-align: center; margin: 1.25rem 0 0.25rem; }
     .hero h1 { font-size: 2rem; line-height: 1.2; margin: 0; }
     .tagline { text-align: center; font-size: 1.05rem; max-width: 60rem; margin: 0.25rem auto 1.25rem; }


   </style>

   <p align="center">
     <!-- Keep both images in the DOM and toggle via CSS -->
     <img src="_static/flowcept-logo.png" alt="Flowcept Logo" width="200" class="logo-light">
     <img src="_static/flowcept-logo-dark.png" alt="Flowcept Logo (Dark)" width="200" class="logo-dark">
   </p>

.. image:: https://img.shields.io/badge/GitHub-Flowcept-black?logo=github&logoColor=white
   :target: https://github.com/ORNL/flowcept
   :alt: GitHub
   :align: center
   :width: 120px

.. raw:: html

   <div class="hero">
     <h4>Lightweight Distributed Workflow Provenance</h4>
   </div>
  <p class="tagline">
     Flowcept captures and queries workflow provenance at runtime with minimal code changes and low overhead.
     It unifies data from diverse tools and workflows across the Edge–Cloud–HPC continuum and provides ML-aware capture,
     MCP agents provenance, telemetry, extensible adapters, and flexible storage.
   </p>

.. important::

   Start here: :doc:`default_user_guide` (recommended first read for workflow developers).
   Full markdown version in repo: `docs/README.md <https://github.com/ORNL/flowcept/blob/main/docs/README.md>`_.


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   default_user_guide
   quick_start
   architecture
   setup
   agent
   prov_capture
   telemetry_capture
   prov_storage
   blob_data
   blob_versioned_single_layer_perceptron_example
   reporting
   prov_query
   rest_api
   schemas
   contributing
   cli-reference
   api-reference
