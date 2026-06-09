"""Small, dependency-free helpers used across modules."""
import uuid
from datetime import datetime, timezone
from typing import Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def resolve_lang(value: Optional[str]) -> str:
    """Normalize incoming language hint to 'ar' or 'en'. Defaults to 'ar'."""
    if not value:
        return "ar"
    v = str(value).strip().lower()
    if v.startswith("en"):
        return "en"
    return "ar"


def lang_directive(lang: str) -> str:
    """Strict output-language override appended to AI system prompts."""
    if resolve_lang(lang) == "en":
        return ("\n\nOUTPUT LANGUAGE OVERRIDE (highest priority): Reply ONLY in clear, modern English. "
                "If the system instructions above use Arabic, IGNORE that language choice and respond in English. "
                "Keep JSON keys exactly as specified; localize only the values/text intended for the user.")
    return ("\n\nتعليمات لغة الإخراج (الأولوية القصوى): ردّ فقط بالعربية الفصحى الواضحة. "
            "احتفظ بمفاتيح JSON كما هي؛ ترجم فقط القيم/النصوص الموجّهة للمستخدم.")


def clean(doc: dict) -> dict:
    """Strip MongoDB's internal _id before returning a document to the client."""
    if doc and "_id" in doc:
        doc.pop("_id", None)
    return doc
