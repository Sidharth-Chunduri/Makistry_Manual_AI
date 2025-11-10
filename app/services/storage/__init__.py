# app/services/storage/__init__.py
"""
Storage backend switcher.

Usage across the codebase stays:
    from app.services import storage

The module decides at import time whether to use Azure or GCP backend
based on the environment variable `STORAGE_BACKEND` ("azure" or "gcp").
Default: "gcp" (since you're migrating).
"""
from app.services.storage_gcp import *  # noqa: F401,F403