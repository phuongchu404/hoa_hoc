"""FastAPI application: REST API + the built React frontend, all on localhost."""
from __future__ import annotations

import logging
import os
import platform
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import warnings  # noqa: E402

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from . import exporters  # noqa: E402
from .chem import io as chem_io  # noqa: E402
from .config import settings  # noqa: E402
from .pipeline import Pipeline, load_image  # noqa: E402
from .schemas import Document, ExportIn, Molecule, MolfileIn, OpenInChemDrawIn, SmilesIn  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("chem")

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    for p in (settings.molscribe_path, settings.rxnscribe_path):
        if not p.exists():
            raise RuntimeError(f"Thiếu model {p}. Chạy: python scripts/download_models.py")
    pipeline = await run_in_threadpool(Pipeline, settings)
    state["pipeline"] = pipeline
    if settings.warmup:
        t = time.perf_counter()
        await run_in_threadpool(pipeline.warmup)
        log.info("warm-up done in %.1fs", time.perf_counter() - t)
    yield
    state.clear()


app = FastAPI(title="ChemImage Converter", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _pipeline() -> Pipeline:
    p = state.get("pipeline")
    if p is None:
        raise HTTPException(503, "Model đang khởi động, thử lại sau vài giây")
    return p


async def _read_image(file: UploadFile):
    data = await file.read()
    if not data:
        raise HTTPException(400, "File rỗng")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Ảnh vượt quá {settings.max_upload_mb} MB")
    try:
        return load_image(data)
    except Exception:
        raise HTTPException(415, "Không đọc được ảnh (hỗ trợ PNG, JPG, GIF, BMP, TIFF, WEBP)")


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# ----------------------------------------------------------------------------- API


@app.get("/api/health")
def health():
    p = state.get("pipeline")
    return {
        "ready": p is not None,
        "device": str(p.device) if p else None,
        "accelerator": str(p.accel) if p and p.accel else None,
        "ocr": bool(p and p.ocr.available),
        "load_seconds": round(p.load_seconds, 1) if p else None,
        "chemdraw": exporters.find_chemdraw(),
        "export_dir": str(settings.export_dir),
        "platform": platform.platform(),
    }


@app.post("/api/recognize", response_model=Document)
async def recognize(file: UploadFile = File(...)):
    image = await _read_image(file)
    return await run_in_threadpool(_pipeline().recognize, image)


@app.post("/api/recognize/region", response_model=Molecule)
async def recognize_region(
    file: UploadFile = File(...),
    x0: float = Form(...), y0: float = Form(...), x1: float = Form(...), y1: float = Form(...),
):
    image = await _read_image(file)
    box = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    mol = await run_in_threadpool(_pipeline().recognize_region, image, box)
    mol.id = f"m-{uuid.uuid4().hex[:6]}"
    return mol


@app.post("/api/molecule/from-molfile", response_model=Molecule)
def molecule_from_molfile(body: MolfileIn):
    built = chem_io.from_molfile(body.molfile)
    return _pipeline().molecule_from_built(
        built, mol_id=body.id or f"m-{uuid.uuid4().hex[:6]}", bbox=body.bbox, source="edited"
    )


@app.post("/api/molecule/from-smiles", response_model=Molecule)
def molecule_from_smiles(body: SmilesIn):
    built = chem_io.from_smiles(body.smiles.strip())
    return _pipeline().molecule_from_built(
        built, mol_id=body.id or f"m-{uuid.uuid4().hex[:6]}", bbox=body.bbox, source="smiles"
    )


@app.post("/api/export")
def export(body: ExportIn):
    content, media, filename = exporters.export(
        body.document, body.format, body.molecule_id, body.reaction_id, body.contract_labels
    )
    return Response(
        content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/chemdraw/open")
def open_in_chemdraw(body: OpenInChemDrawIn):
    content, _, filename = exporters.export(
        body.document, "cdxml", body.molecule_id, None, body.contract_labels
    )
    return exporters.save_and_open(content, filename, settings.export_dir)


# ----------------------------------------------------------------------------- frontend

dist: Path = settings.frontend_dist
if (dist / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = (dist / path).resolve()
        if path and target.is_file() and dist.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(dist / "index.html")
else:

    @app.get("/", include_in_schema=False)
    def no_frontend():
        return JSONResponse(
            {"detail": "Frontend chưa được build. Chạy: cd frontend && npm install && npm run build"}
        )
