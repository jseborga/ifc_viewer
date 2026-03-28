import json
import logging
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
LOGGER = logging.getLogger("ifc_converter_service")


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
SHARED_TOKEN = os.getenv("SHARED_TOKEN", "").strip()
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "/data")).resolve()
VERIFY_SSL = env_bool("VERIFY_SSL", True)
PORT = int(os.getenv("PORT", "8080"))
IFC_CONVERT_BIN = os.getenv("IFC_CONVERT_BIN", "IfcConvert")
DOWNLOAD_TIMEOUT = float(os.getenv("DOWNLOAD_TIMEOUT", "300"))
CALLBACK_TIMEOUT = float(os.getenv("CALLBACK_TIMEOUT", "60"))

app = FastAPI(title="IFC Converter Service", version="1.0.0")
jobs_lock = threading.Lock()
jobs: Dict[str, Dict[str, Any]] = {}


class ConversionJobRequest(BaseModel):
    version_id: int
    model_name: Optional[str] = None
    source_filename: Optional[str] = None
    ifc_download_url: str
    callback_url: str
    access_token: str
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    height: Optional[float] = None
    heading: Optional[float] = None
    pitch: Optional[float] = None
    roll: Optional[float] = None


def extract_token(authorization: Optional[str], x_bim_token: Optional[str]) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1].strip()
    return (x_bim_token or "").strip()


def require_shared_token(authorization: Optional[str], x_bim_token: Optional[str]) -> None:
    token = extract_token(authorization, x_bim_token)
    if not SHARED_TOKEN or token != SHARED_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid shared token")


def update_job(job_id: str, **values: Any) -> None:
    with jobs_lock:
        current = jobs.setdefault(job_id, {})
        current.update(values)


def safe_filename(name: Optional[str], default: str) -> str:
    raw = (name or default).strip().replace("\\", "_").replace("/", "_")
    return raw or default


def ensure_storage() -> None:
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    (STORAGE_ROOT / "jobs").mkdir(parents=True, exist_ok=True)
    (STORAGE_ROOT / "tiles").mkdir(parents=True, exist_ok=True)


def run_command(command: List[str], cwd: Path) -> str:
    LOGGER.info("Running command: %s", " ".join(command))
    result = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    log_text = f"$ {' '.join(command)}\n{result.stdout}\n{result.stderr}".strip()
    if result.returncode != 0:
        raise RuntimeError(log_text)
    return log_text


def download_ifc(payload: ConversionJobRequest, target: Path) -> str:
    headers = {
        "Authorization": f"Bearer {payload.access_token}",
        "X-BIM-Token": payload.access_token,
    }
    with httpx.Client(timeout=DOWNLOAD_TIMEOUT, verify=VERIFY_SSL, follow_redirects=True) as client:
        response = client.get(payload.ifc_download_url, headers=headers)
        response.raise_for_status()
        target.write_bytes(response.content)
        return f"Downloaded {len(response.content)} bytes from {payload.ifc_download_url}"


def build_tileset(job_id: str, payload: ConversionJobRequest) -> Tuple[str, str]:
    ensure_storage()
    job_root = STORAGE_ROOT / "jobs" / job_id
    tiles_root = STORAGE_ROOT / "tiles" / str(payload.version_id)

    if job_root.exists():
        shutil.rmtree(job_root)
    job_root.mkdir(parents=True, exist_ok=True)

    if tiles_root.exists():
        shutil.rmtree(tiles_root)
    tiles_root.mkdir(parents=True, exist_ok=True)

    source_name = safe_filename(payload.source_filename, f"version_{payload.version_id}.ifc")
    if not source_name.lower().endswith(".ifc"):
        source_name = f"{source_name}.ifc"
    ifc_path = job_root / source_name
    glb_path = job_root / "model.glb"
    b3dm_path = tiles_root / "model.b3dm"
    tileset_path = tiles_root / "tileset.json"

    logs = [
        download_ifc(payload, ifc_path),
        run_command([IFC_CONVERT_BIN, str(ifc_path), str(glb_path)], cwd=job_root),
        run_command(
            ["npx", "3d-tiles-tools", "glbToB3dm", "-i", str(glb_path), "-o", str(b3dm_path)],
            cwd=job_root,
        ),
    ]

    create_tileset_command = [
        "npx",
        "3d-tiles-tools",
        "createTilesetJson",
        "-i",
        str(tiles_root),
        "-o",
        str(tileset_path),
    ]
    if payload.longitude is not None and payload.latitude is not None:
        create_tileset_command.extend(
            [
                "--cartographicPositionDegrees",
                str(payload.longitude),
                str(payload.latitude),
                str(payload.height or 0),
            ]
        )
        create_tileset_command.extend(
            [
                "--rotationDegrees",
                str(payload.heading or 0),
                str(payload.pitch or 0),
                str(payload.roll or 0),
            ]
        )
    logs.append(run_command(create_tileset_command, cwd=job_root))

    tileset_url = f"{PUBLIC_BASE_URL}/tiles/{payload.version_id}/tileset.json"
    return tileset_url, "\n\n".join(logs)


def callback_odoo(payload: ConversionJobRequest, body: Dict[str, Any]) -> None:
    headers = {
        "Authorization": f"Bearer {payload.access_token}",
        "X-BIM-Token": payload.access_token,
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=CALLBACK_TIMEOUT, verify=VERIFY_SSL) as client:
        response = client.post(payload.callback_url, headers=headers, json=body)
        response.raise_for_status()


def process_job(job_id: str, payload_dict: Dict[str, Any]) -> None:
    payload = ConversionJobRequest(**payload_dict)
    update_job(job_id, status="processing", version_id=payload.version_id)
    try:
        tileset_url, conversion_log = build_tileset(job_id, payload)
        callback_body = {
            "version_id": payload.version_id,
            "status": "ready",
            "job_id": job_id,
            "tileset_url": tileset_url,
            "conversion_log": conversion_log,
            "error_message": "",
        }
        callback_odoo(payload, callback_body)
        update_job(job_id, status="ready", tileset_url=tileset_url)
    except Exception as exc:
        LOGGER.exception("Conversion job failed")
        callback_body = {
            "version_id": payload.version_id,
            "status": "error",
            "job_id": job_id,
            "tileset_url": "",
            "conversion_log": str(exc),
            "error_message": str(exc),
        }
        try:
            callback_odoo(payload, callback_body)
        except Exception:
            LOGGER.exception("Callback to Odoo failed after conversion error")
        update_job(job_id, status="error", error_message=str(exc))


@app.on_event("startup")
def startup() -> None:
    if not PUBLIC_BASE_URL:
        LOGGER.warning("PUBLIC_BASE_URL is empty; tileset URLs will be invalid until it is set.")
    ensure_storage()


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "public_base_url": PUBLIC_BASE_URL,
        "storage_root": str(STORAGE_ROOT),
        "ifc_convert_bin": IFC_CONVERT_BIN,
    }


@app.post("/jobs")
def create_job(
    payload: ConversionJobRequest,
    authorization: Optional[str] = Header(default=None),
    x_bim_token: Optional[str] = Header(default=None, alias="X-BIM-Token"),
) -> Dict[str, Any]:
    require_shared_token(authorization, x_bim_token)
    job_id = uuid.uuid4().hex
    update_job(job_id, status="accepted", version_id=payload.version_id)
    worker = threading.Thread(target=process_job, args=(job_id, payload.model_dump()), daemon=True)
    worker.start()
    return {"status": "processing", "job_id": job_id}


@app.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    authorization: Optional[str] = Header(default=None),
    x_bim_token: Optional[str] = Header(default=None, alias="X-BIM-Token"),
) -> Dict[str, Any]:
    require_shared_token(authorization, x_bim_token)
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/tiles/{version_id}/{resource_path:path}")
def get_tile(version_id: int, resource_path: str) -> FileResponse:
    base_dir = (STORAGE_ROOT / "tiles" / str(version_id)).resolve()
    target = (base_dir / resource_path).resolve()
    if base_dir not in target.parents and target != base_dir:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Resource not found")
    return FileResponse(target)
