"""Pytest configuration for backend tests.

Adds the backend directory to sys.path so that `import app.*` works
without installing the package.
"""
import sys
import os

# backend/ directory (parent of app/)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
