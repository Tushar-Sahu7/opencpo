"""Receipts plugin — re-exports receipt routes (mandatory feature)."""
from routes.receipt import router

__all__ = ["router"]
