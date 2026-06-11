# Configuration file for the Sphinx documentation builder.
#
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
project = "Flowcept"
copyright = "Oak Ridge National Lab"
author = "Oak Ridge National Lab"

# -- General configuration ---------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
]
autosummary_generate = True
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Reusable base URL for intra-doc links in .rst files.
rst_epilog = """
.. |docs_base| replace:: https://flowcept.readthedocs.io/en/latest
"""

# -- HTML output -------------------------------------------------------------
html_theme = "furo"
html_title = "Flowcept"

# Keep using your existing 'img' folder as the static path so you don't have to move files.
# Sphinx will treat everything inside 'img/' as static assets.
html_static_path = ["img"]
html_extra_path = ["openapi"]

# Furo supports automatic dark/light logo switching.
# IMPORTANT: Paths below are relative to the *root* of each static path ('img' here),
# so do NOT prefix with 'img/'.
html_theme_options = {
    "light_logo": "flowcept-logo.png",
    "dark_logo": "flowcept-logo-dark.png",
    # Optional extras:
    "sidebar_hide_name": True,
    # "light_css_variables": {},
    # "dark_css_variables": {},
}

# html_logo = "img/flowcept-logo.png
