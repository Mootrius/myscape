"""Shared slowapi Limiter instance.

Lives in its own module so both app/main.py (which wires it into the
FastAPI app) and app/routers/linking.py (which decorates a specific
endpoint with it) can import it without a circular import.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
