"""Reusable FastAPI dependencies."""
from typing import Optional
from fastapi import Header

from app.core.utils import resolve_lang


def get_lang(x_lang: Optional[str] = Header(default=None, alias="X-Lang")) -> str:
    """Extract language preference from the X-Lang request header (defaults to 'ar')."""
    return resolve_lang(x_lang)
