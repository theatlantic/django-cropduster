"""Sphinx configuration for django-cropduster."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
match = re.search(
    r'''__version__\s*=\s*['"]([^'"]+)['"]''',
    (ROOT / "cropduster" / "__init__.py").read_text(),
)
if match is None:
    raise RuntimeError("cropduster.__version__ was not found")

project = "django-cropduster"
author = "The Atlantic"
copyright = "2015–2026, The Atlantic"
release = match.group(1)
version = ".".join(release.split(".")[:2])

root_doc = "index"
language = "en"
exclude_patterns = ["_build"]
html_theme = "sphinx_rtd_theme"
html_static_path = []
