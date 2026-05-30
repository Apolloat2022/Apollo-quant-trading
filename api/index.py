"""
Vercel serverless entry point.
Adds the project root to sys.path so all sibling modules resolve correctly,
then re-exports the Flask app as the WSGI handler Vercel expects.
"""

import os
import sys

# Project root is one level up from this file (api/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.app import app  # noqa: F401  — Vercel picks up 'app' by name
