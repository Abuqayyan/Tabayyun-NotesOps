"""Project file attachments: upload / list / download / delete (on-disk storage)."""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse

from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.utils import now_iso, new_id
from app.shared.files import UPLOAD_DIR, MAX_UPLOAD_BYTES, safe_filename
from app.shared.activity import emit_activity

log = logging.getLogger("opscore.files")
router = APIRouter()


@router.post("/projects/{pid}/files")
async def upload_project_file(pid: str, file: UploadFile = File(...), user=Depends(get_current_user)):
    project = await db.projects.find_one({"id": pid, "members": user["id"]}, {"_id": 0, "id": 1})
    if not project:
        raise HTTPException(404, "Project not found")
    data = await file.read()
    size = len(data)
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
    if size == 0:
        raise HTTPException(400, "Empty file")
    fid = new_id()
    safe = safe_filename(file.filename or "file")
    proj_dir = UPLOAD_DIR / pid
    proj_dir.mkdir(parents=True, exist_ok=True)
    disk_path = proj_dir / f"{fid}__{safe}"
    disk_path.write_bytes(data)
    doc = {
        "id": fid,
        "project_id": pid,
        "owner_id": user["id"],
        "filename": safe,
        "content_type": file.content_type or "application/octet-stream",
        "size": size,
        "storage_path": str(disk_path),
        "uploaded_at": now_iso(),
    }
    await db.project_files.insert_one(doc)
    await emit_activity(user["id"], "file.uploaded", "project", pid, project_id=pid,
                        actor_name=user.get("name"), metadata={"filename": safe})
    doc.pop("_id", None); doc.pop("storage_path", None)
    return doc


@router.get("/projects/{pid}/files")
async def list_project_files(pid: str, user=Depends(get_current_user)):
    project = await db.projects.find_one({"id": pid, "members": user["id"]}, {"_id": 0, "id": 1})
    if not project:
        raise HTTPException(404, "Project not found")
    rows = await db.project_files.find({"project_id": pid}, {"_id": 0, "storage_path": 0}).sort("uploaded_at", -1).to_list(200)
    return rows


@router.get("/projects/{pid}/files/{fid}/download")
async def download_project_file(pid: str, fid: str, user=Depends(get_current_user)):
    project = await db.projects.find_one({"id": pid, "members": user["id"]}, {"_id": 0, "id": 1})
    if not project:
        raise HTTPException(404, "Project not found")
    rec = await db.project_files.find_one({"id": fid, "project_id": pid}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "File not found")
    p = Path(rec["storage_path"])
    if not p.exists():
        raise HTTPException(404, "File missing on disk")
    return FileResponse(path=str(p), filename=rec["filename"], media_type=rec.get("content_type", "application/octet-stream"))


@router.delete("/projects/{pid}/files/{fid}")
async def delete_project_file(pid: str, fid: str, user=Depends(get_current_user)):
    project = await db.projects.find_one({"id": pid, "members": user["id"]}, {"_id": 0, "id": 1})
    if not project:
        raise HTTPException(404, "Project not found")
    rec = await db.project_files.find_one({"id": fid, "project_id": pid}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "File not found")
    try:
        p = Path(rec["storage_path"])
        if p.exists():
            p.unlink()
    except Exception as e:  # noqa: BLE001
        log.warning(f"file unlink failed: {e}")
    await db.project_files.delete_one({"id": fid})
    return {"ok": True}
