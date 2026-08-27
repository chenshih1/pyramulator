"""Sphinx configuration for pyramulator documentation."""

from __future__ import annotations

import os
import sys

# Allow autodoc to import the package without building the C++ extension.
sys.path.insert(0, os.path.abspath(".."))

project = "pyramulator"
copyright = "pyramulator contributors"
author = "pyramulator contributors"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "alabaster"
html_static_path = []

autodoc_member_order = "bysource"
napoleon_google_docstring = True
napoleon_numpy_docstring = False
