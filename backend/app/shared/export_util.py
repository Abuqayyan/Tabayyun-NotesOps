"""Tabular export helpers — CSV (always) and XLSX (best-effort via openpyxl).

CSV uses only the stdlib so it works everywhere. XLSX is attempted with openpyxl if it is
installed; otherwise we transparently fall back to CSV (and signal it in a header), so the
endpoint never hard-fails on a missing optional dependency.
"""
import csv
import io
import logging
from typing import List, Dict, Any

from fastapi.responses import StreamingResponse

log = logging.getLogger("opscore.export")


def _flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        import json
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def csv_response(filename: str, headers: List[str], rows: List[Dict[str, Any]]) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        writer.writerow([_flatten(r.get(h)) for h in headers])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"', "X-Export-Rows": str(len(rows))},
    )


def xlsx_response(filename: str, headers: List[str], rows: List[Dict[str, Any]]):
    """Return an XLSX StreamingResponse, or None if openpyxl is unavailable (caller falls back)."""
    try:
        from openpyxl import Workbook
    except Exception:  # noqa: BLE001 - optional dependency
        return None
    wb = Workbook()
    ws = wb.active
    ws.title = filename[:31] or "export"
    ws.append(headers)
    for r in rows:
        ws.append([_flatten(r.get(h)) for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"', "X-Export-Rows": str(len(rows))},
    )


def tabular_response(fmt: str, filename: str, headers: List[str], rows: List[Dict[str, Any]]) -> StreamingResponse:
    if (fmt or "csv").lower() == "xlsx":
        resp = xlsx_response(filename, headers, rows)
        if resp is not None:
            return resp
        log.info("openpyxl unavailable — falling back to CSV")
        out = csv_response(filename, headers, rows)
        out.headers["X-Export-Fallback"] = "csv"
        return out
    return csv_response(filename, headers, rows)
