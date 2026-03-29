import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    import ifcopenshell
    from ifcopenshell.util.element import get_psets
except Exception:  # pragma: no cover - runtime availability depends on image
    ifcopenshell = None
    get_psets = None

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
LOGGER = logging.getLogger("ifc_converter_service")


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
SHARED_TOKEN = os.getenv("SHARED_TOKEN", "").strip()
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "/data")).resolve()
VERIFY_SSL = env_bool("VERIFY_SSL", True)
PORT = int(os.getenv("PORT", "8080"))
IFC_CONVERT_BIN = os.getenv("IFC_CONVERT_BIN", "IfcConvert")
DOWNLOAD_TIMEOUT = float(os.getenv("DOWNLOAD_TIMEOUT", "300"))
CALLBACK_TIMEOUT = float(os.getenv("CALLBACK_TIMEOUT", "60"))
CONVERTER_MODE = os.getenv("CONVERTER_MODE", "self_hosted").strip() or "self_hosted"
DEFAULT_VALIDATION_LEVEL = os.getenv("VALIDATION_LEVEL", "standard").strip() or "standard"
MAX_METADATA_ELEMENTS = env_int("MAX_METADATA_ELEMENTS", 1000)
MAX_PROPERTIES_PER_ELEMENT = env_int("MAX_PROPERTIES_PER_ELEMENT", 40)
VISUALIZATION_FORMAT = os.getenv("VISUALIZATION_FORMAT", "3dtiles-b3dm-legacy").strip() or "3dtiles-b3dm-legacy"

app = FastAPI(title="IFC Converter Service", version="2.0.0")
jobs_lock = threading.Lock()
jobs: Dict[str, Dict[str, Any]] = {}


class ConversionJobRequest(BaseModel):
    version_id: int
    model_name: Optional[str] = None
    source_filename: Optional[str] = None
    ifc_download_url: str
    callback_url: str
    access_token: str
    metadata_mode: Optional[str] = None
    requested_streaming_format: Optional[str] = None
    preferred_content_format: Optional[str] = None
    legacy_b3dm_fallback: bool = True
    validation_level: Optional[str] = None
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


def write_json_file(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in list(value)]
    return str(value)


def flatten_psets(product: Any) -> Dict[str, Any]:
    if get_psets is None:
        return {}

    try:
        raw_psets = get_psets(product, psets_only=False, qtos=True, should_inherit=False)
    except TypeError:
        raw_psets = get_psets(product)
    except Exception:
        LOGGER.exception("Failed to extract property sets for product %s", getattr(product, "GlobalId", "?"))
        return {}

    flattened: Dict[str, Any] = {}
    for group_name, group_values in (raw_psets or {}).items():
        if not isinstance(group_values, dict):
            continue
        for prop_name, prop_value in group_values.items():
            if prop_name == "id":
                continue
            flattened["%s.%s" % (group_name, prop_name)] = json_safe(prop_value)
            if len(flattened) >= MAX_PROPERTIES_PER_ELEMENT:
                return flattened
    return flattened


def increment_counter(counter: Dict[str, int], key: Optional[str]) -> None:
    normalized = (key or "Unspecified").strip() or "Unspecified"
    counter[normalized] = counter.get(normalized, 0) + 1


def collect_material_names(material: Any) -> List[str]:
    if material is None:
        return []

    names: List[str] = []
    material_type = material.is_a()

    if material_type == "IfcMaterial":
        if getattr(material, "Name", None):
            names.append(material.Name)
    elif material_type == "IfcMaterialList":
        for item in getattr(material, "Materials", []) or []:
            names.extend(collect_material_names(item))
    elif material_type == "IfcMaterialLayerSetUsage":
        names.extend(collect_material_names(getattr(material, "ForLayerSet", None)))
    elif material_type == "IfcMaterialLayerSet":
        for layer in getattr(material, "MaterialLayers", []) or []:
            names.extend(collect_material_names(getattr(layer, "Material", None)))
    elif material_type == "IfcMaterialConstituentSet":
        for constituent in getattr(material, "MaterialConstituents", []) or []:
            names.extend(collect_material_names(getattr(constituent, "Material", None)))
    elif material_type == "IfcMaterialProfileSetUsage":
        names.extend(collect_material_names(getattr(material, "ForProfileSet", None)))
    elif material_type == "IfcMaterialProfileSet":
        for profile in getattr(material, "MaterialProfiles", []) or []:
            names.extend(collect_material_names(getattr(profile, "Material", None)))
    elif getattr(material, "Name", None):
        names.append(material.Name)

    unique_names: List[str] = []
    seen = set()
    for name in names:
        if name and name not in seen:
            unique_names.append(name)
            seen.add(name)
    return unique_names


def extract_level_name(product: Any) -> Optional[str]:
    for relation in getattr(product, "ContainedInStructure", []) or []:
        structure = getattr(relation, "RelatingStructure", None)
        if structure and getattr(structure, "Name", None):
            return structure.Name
    return None


def extract_system_name(product: Any) -> Optional[str]:
    for relation in getattr(product, "HasAssignments", []) or []:
        group = getattr(relation, "RelatingGroup", None)
        if group and group.is_a("IfcSystem") and getattr(group, "Name", None):
            return group.Name
    return None


def infer_discipline(ifc_class: Optional[str]) -> str:
    class_name = (ifc_class or "").lower()
    if any(token in class_name for token in ("beam", "column", "slab", "wall", "footing", "pile")):
        return "structure"
    if any(token in class_name for token in ("duct", "pipe", "cable", "flow", "terminal")):
        return "mep"
    if any(token in class_name for token in ("road", "bridge", "terrain", "site")):
        return "civil"
    if class_name:
        return "architecture"
    return "other"


def extract_metadata(ifc_path: Path, payload: ConversionJobRequest) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    summary: Dict[str, Any] = {
        "metadata_mode": payload.metadata_mode or "external_by_global_id",
        "ifc_schema": None,
        "total_products": 0,
        "exported_elements": 0,
        "metadata_truncated": False,
        "class_breakdown": {},
        "level_breakdown": {},
        "system_breakdown": {},
        "warnings": [],
    }

    if ifcopenshell is None:
        summary["warnings"].append("ifcopenshell Python module is not available in the runtime image.")
        return [], summary

    model = ifcopenshell.open(str(ifc_path))
    summary["ifc_schema"] = getattr(model, "schema", None)

    class_counts: Dict[str, int] = {}
    level_counts: Dict[str, int] = {}
    system_counts: Dict[str, int] = {}
    elements: List[Dict[str, Any]] = []

    for product in model.by_type("IfcProduct"):
        summary["total_products"] += 1
        global_id = getattr(product, "GlobalId", None)
        if not global_id:
            continue
        if MAX_METADATA_ELEMENTS > 0 and len(elements) >= MAX_METADATA_ELEMENTS:
            summary["metadata_truncated"] = True
            break

        ifc_class = product.is_a()
        level_name = extract_level_name(product)
        system_name = extract_system_name(product)
        material_names: List[str] = []
        for association in getattr(product, "HasAssociations", []) or []:
            if association.is_a("IfcRelAssociatesMaterial"):
                material_names.extend(collect_material_names(getattr(association, "RelatingMaterial", None)))

        properties = flatten_psets(product)

        increment_counter(class_counts, ifc_class)
        increment_counter(level_counts, level_name)
        increment_counter(system_counts, system_name)

        elements.append(
            {
                "global_id": global_id,
                "source_uid": str(product.id()),
                "name": getattr(product, "Name", None),
                "ifc_class": ifc_class,
                "object_type": getattr(product, "ObjectType", None),
                "predefined_type": str(getattr(product, "PredefinedType", "")) or None,
                "level_name": level_name,
                "system_name": system_name,
                "discipline": infer_discipline(ifc_class),
                "material_names": material_names,
                "is_spatial": bool(
                    product.is_a("IfcSpatialElement") or product.is_a("IfcSpatialStructureElement")
                ),
                "properties": properties,
            }
        )

    summary["exported_elements"] = len(elements)
    summary["class_breakdown"] = class_counts
    summary["level_breakdown"] = level_counts
    summary["system_breakdown"] = system_counts
    return elements, summary


def collect_tileset_resource_paths(tile: Dict[str, Any], resources: List[str]) -> None:
    content = tile.get("content") or {}
    if isinstance(content, dict):
        uri = content.get("uri") or content.get("url")
        if uri:
            resources.append(uri)

    for item in tile.get("contents") or []:
        if isinstance(item, dict):
            uri = item.get("uri") or item.get("url")
            if uri:
                resources.append(uri)

    for child in tile.get("children") or []:
        if isinstance(child, dict):
            collect_tileset_resource_paths(child, resources)


def build_validation_summary(checks: List[Dict[str, str]]) -> Tuple[str, str]:
    failed = [check for check in checks if check["status"] == "failed"]
    warnings = [check for check in checks if check["status"] == "warning"]
    if failed:
        return "failed", "Validation failed: %s" % "; ".join(check["name"] for check in failed)
    if warnings:
        return "warning", "Validation completed with warnings: %s" % "; ".join(
            check["name"] for check in warnings
        )
    return "passed", "Validation passed."


def validate_visual_package(
    tiles_root: Path,
    tileset_path: Path,
    payload: ConversionJobRequest,
    visualization_format: str,
) -> Dict[str, Any]:
    checks: List[Dict[str, str]] = []
    tileset_json: Dict[str, Any] = {}

    if tileset_path.exists():
        checks.append({"name": "tileset_exists", "status": "passed", "details": str(tileset_path)})
    else:
        checks.append({"name": "tileset_exists", "status": "failed", "details": "tileset.json not found"})
        status, summary = build_validation_summary(checks)
        return {"status": status, "summary": summary, "checks": checks}

    try:
        tileset_json = json.loads(tileset_path.read_text(encoding="utf-8"))
        checks.append({"name": "tileset_parseable", "status": "passed", "details": "JSON parsed correctly"})
    except Exception as exc:
        checks.append({"name": "tileset_parseable", "status": "failed", "details": str(exc)})
        status, summary = build_validation_summary(checks)
        return {"status": status, "summary": summary, "checks": checks}

    root = tileset_json.get("root") or {}
    if root:
        checks.append({"name": "tileset_root_present", "status": "passed", "details": "Root tile present"})
    else:
        checks.append({"name": "tileset_root_present", "status": "failed", "details": "Missing root tile"})

    resources: List[str] = []
    collect_tileset_resource_paths(root, resources)
    missing = []
    for resource in resources:
        if not (tiles_root / resource).exists():
            missing.append(resource)
    if missing:
        checks.append(
            {
                "name": "resource_accessibility",
                "status": "failed",
                "details": "Missing resources: %s" % ", ".join(sorted(missing)),
            }
        )
    else:
        checks.append(
            {
                "name": "resource_accessibility",
                "status": "passed",
                "details": "%s resource(s) resolved" % len(resources),
            }
        )

    if any(resource.lower().endswith(".b3dm") for resource in resources):
        checks.append(
            {
                "name": "legacy_b3dm_content",
                "status": "warning",
                "details": "The current package still relies on legacy b3dm content.",
            }
        )
    else:
        checks.append(
            {
                "name": "modern_content_format",
                "status": "passed",
                "details": "No legacy b3dm content detected.",
            }
        )

    if payload.longitude is not None and payload.latitude is not None:
        checks.append(
            {
                "name": "georeference_input",
                "status": "passed",
                "details": "Cartographic position supplied in the conversion payload.",
            }
        )
    else:
        checks.append(
            {
                "name": "georeference_input",
                "status": "warning",
                "details": "No explicit geographic coordinates were supplied.",
            }
        )

    if root.get("transform"):
        checks.append(
            {
                "name": "spatial_transform",
                "status": "passed",
                "details": "Root transform present in tileset.",
            }
        )
    else:
        checks.append(
            {
                "name": "spatial_transform",
                "status": "warning",
                "details": "No root transform was found in tileset.json.",
            }
        )

    status, summary = build_validation_summary(checks)
    return {
        "status": status,
        "summary": summary,
        "checks": checks,
        "tileset_asset_version": ((tileset_json.get("asset") or {}).get("version") or "1.0"),
        "resource_count": len(resources),
        "tileset_size_bytes": tileset_path.stat().st_size,
        "visualization_format": visualization_format,
    }


def build_visual_package_manifest(
    job_id: str,
    payload: ConversionJobRequest,
    ifc_path: Path,
    tiles_root: Path,
    validation_report: Dict[str, Any],
    metadata_summary: Dict[str, Any],
) -> Dict[str, Any]:
    files = []
    for file_path in sorted(tiles_root.rglob("*")):
        if file_path.is_file():
            files.append(
                {
                    "path": str(file_path.relative_to(tiles_root)).replace("\\", "/"),
                    "size_bytes": file_path.stat().st_size,
                }
            )

    return {
        "job_id": job_id,
        "generated_at": utc_now_iso(),
        "converter_mode": CONVERTER_MODE,
        "visualization_format": validation_report.get("visualization_format") or VISUALIZATION_FORMAT,
        "tileset_spec_version": validation_report.get("tileset_asset_version") or "1.0",
        "requested_streaming_format": payload.requested_streaming_format or "3dtiles",
        "preferred_content_format": payload.preferred_content_format or "gltf_glb",
        "metadata_mode": payload.metadata_mode or "external_by_global_id",
        "validation_status": validation_report.get("status"),
        "validation_level": payload.validation_level or DEFAULT_VALIDATION_LEVEL,
        "source_filename": payload.source_filename,
        "source_sha256": sha256_file(ifc_path),
        "metadata_summary": metadata_summary,
        "files": files,
    }


def download_ifc(payload: ConversionJobRequest, target: Path) -> str:
    headers = {
        "Authorization": "Bearer %s" % payload.access_token,
        "X-BIM-Token": payload.access_token,
    }
    with httpx.Client(timeout=DOWNLOAD_TIMEOUT, verify=VERIFY_SSL, follow_redirects=True) as client:
        response = client.get(payload.ifc_download_url, headers=headers)
        response.raise_for_status()
        target.write_bytes(response.content)
        return "Downloaded %s bytes from %s" % (len(response.content), payload.ifc_download_url)


def build_visual_package(job_id: str, payload: ConversionJobRequest) -> Dict[str, Any]:
    ensure_storage()
    job_root = STORAGE_ROOT / "jobs" / job_id
    tiles_root = STORAGE_ROOT / "tiles" / str(payload.version_id)

    if job_root.exists():
        shutil.rmtree(job_root)
    job_root.mkdir(parents=True, exist_ok=True)

    if tiles_root.exists():
        shutil.rmtree(tiles_root)
    tiles_root.mkdir(parents=True, exist_ok=True)

    source_name = safe_filename(payload.source_filename, "version_%s.ifc" % payload.version_id)
    if not source_name.lower().endswith(".ifc"):
        source_name = "%s.ifc" % source_name
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

    element_metadata, metadata_summary = extract_metadata(ifc_path, payload)
    write_json_file(
        tiles_root / "element-metadata.json",
        {
            "version_id": payload.version_id,
            "metadata_mode": payload.metadata_mode or "external_by_global_id",
            "summary": metadata_summary,
            "items": element_metadata,
        },
    )
    write_json_file(tiles_root / "metadata-summary.json", metadata_summary)

    validation_report = validate_visual_package(
        tiles_root,
        tileset_path,
        payload,
        visualization_format=VISUALIZATION_FORMAT,
    )
    write_json_file(tiles_root / "validation-report.json", validation_report)

    visual_package_manifest = build_visual_package_manifest(
        job_id=job_id,
        payload=payload,
        ifc_path=ifc_path,
        tiles_root=tiles_root,
        validation_report=validation_report,
        metadata_summary=metadata_summary,
    )
    write_json_file(tiles_root / "visual-package-manifest.json", visual_package_manifest)

    tileset_url = "%s/tiles/%s/tileset.json" % (PUBLIC_BASE_URL, payload.version_id)
    metadata_url = "%s/tiles/%s/element-metadata.json" % (PUBLIC_BASE_URL, payload.version_id)

    return {
        "tileset_url": tileset_url,
        "metadata_url": metadata_url,
        "conversion_log": "\n\n".join(logs),
        "visualization_format": VISUALIZATION_FORMAT,
        "tileset_spec_version": validation_report.get("tileset_asset_version") or "1.0",
        "validation_status": validation_report.get("status"),
        "validation_summary": validation_report.get("summary"),
        "validation_report": validation_report,
        "visual_package_manifest": visual_package_manifest,
        "metadata_summary": metadata_summary,
        "element_metadata": element_metadata,
        "element_count": metadata_summary.get("exported_elements", 0),
        "metadata_truncated": metadata_summary.get("metadata_truncated", False),
    }


def callback_odoo(payload: ConversionJobRequest, body: Dict[str, Any]) -> None:
    headers = {
        "Authorization": "Bearer %s" % payload.access_token,
        "X-BIM-Token": payload.access_token,
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=CALLBACK_TIMEOUT, verify=VERIFY_SSL) as client:
        response = client.post(payload.callback_url, headers=headers, json=body)
        response.raise_for_status()


def process_job(job_id: str, payload_dict: Dict[str, Any]) -> None:
    payload = ConversionJobRequest(**payload_dict)
    update_job(
        job_id,
        status="processing",
        version_id=payload.version_id,
        converter_mode=CONVERTER_MODE,
    )
    try:
        result = build_visual_package(job_id, payload)
        final_status = "ready" if result.get("validation_status") != "failed" else "error"
        callback_body = {
            "version_id": payload.version_id,
            "status": final_status,
            "job_id": job_id,
            "tileset_url": result["tileset_url"],
            "conversion_log": result["conversion_log"],
            "error_message": "" if final_status == "ready" else result.get("validation_summary") or "",
            "visualization_format": result.get("visualization_format"),
            "tileset_spec_version": result.get("tileset_spec_version"),
            "validation_status": result.get("validation_status"),
            "validation_summary": result.get("validation_summary"),
            "validation_report": result.get("validation_report"),
            "visual_package_manifest": result.get("visual_package_manifest"),
            "metadata_summary": result.get("metadata_summary"),
            "element_metadata": result.get("element_metadata"),
            "element_count": result.get("element_count"),
            "metadata_truncated": result.get("metadata_truncated"),
            "metadata_url": result.get("metadata_url"),
        }
        callback_odoo(payload, callback_body)
        update_job(
            job_id,
            status=final_status,
            tileset_url=result.get("tileset_url"),
            validation_status=result.get("validation_status"),
            element_count=result.get("element_count"),
        )
    except Exception as exc:
        LOGGER.exception("Conversion job failed")
        callback_body = {
            "version_id": payload.version_id,
            "status": "error",
            "job_id": job_id,
            "tileset_url": "",
            "conversion_log": str(exc),
            "error_message": str(exc),
            "validation_status": "failed",
        }
        try:
            callback_odoo(payload, callback_body)
        except Exception:
            LOGGER.exception("Callback to Odoo failed after conversion error")
        update_job(job_id, status="error", error_message=str(exc), validation_status="failed")


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
        "converter_mode": CONVERTER_MODE,
        "visualization_format": VISUALIZATION_FORMAT,
        "validation_level": DEFAULT_VALIDATION_LEVEL,
        "max_metadata_elements": MAX_METADATA_ELEMENTS,
    }


@app.post("/jobs")
def create_job(
    payload: ConversionJobRequest,
    authorization: Optional[str] = Header(default=None),
    x_bim_token: Optional[str] = Header(default=None, alias="X-BIM-Token"),
) -> Dict[str, Any]:
    require_shared_token(authorization, x_bim_token)
    job_id = uuid.uuid4().hex
    update_job(
        job_id,
        status="accepted",
        version_id=payload.version_id,
        converter_mode=CONVERTER_MODE,
        metadata_mode=payload.metadata_mode or "external_by_global_id",
    )
    worker = threading.Thread(target=process_job, args=(job_id, payload.model_dump()), daemon=True)
    worker.start()
    return {
        "status": "processing",
        "job_id": job_id,
        "converter_mode": CONVERTER_MODE,
        "visualization_format": VISUALIZATION_FORMAT,
    }


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
