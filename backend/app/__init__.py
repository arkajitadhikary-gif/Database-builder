"""Judicore backend package initialization."""

import asyncio
import sys
import warnings

if sys.platform == "win32":
    # psycopg's async driver requires a selector loop on Windows.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        # Keeps imports portable to non-Windows Python implementations.
        pass
