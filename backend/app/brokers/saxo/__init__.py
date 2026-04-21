"""Saxo Bank OpenAPI adapter.

All Saxo-specific code lives in this package. Nothing outside this package
should import from `saxo.*` except `registry.py` which wires the adapter in.
"""
from app.brokers.saxo.adapter import SaxoAdapter

__all__ = ["SaxoAdapter"]
