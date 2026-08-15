"""Test-runtime compatibility for psycopg async connections on Windows."""

import asyncio
import sys
import warnings

if sys.platform == "win32":
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass
