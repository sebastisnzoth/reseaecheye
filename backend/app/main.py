"""ImageTrace OSINT: local image forensics; no face recognition or web scraping."""
import hashlib
import io
import json
import os
import secrets
import base64
import threading
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import ipaddress
import socket

import imagehash
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from PIL import Image, ImageOps, ImageChops, ImageEnhance, UnidentifiedImageError
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

DATA = Path(os.getenv("DATA_DIR", "./data")).resolve()
MAX_BYTES = int(os.getenv("MAX_IMAGE_BYTES", "10485760"))
RETENTION_HOURS = int(os.getenv("RETENTION_HOURS", "24"))
ALLOWED_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / "imagetrace.sqlite3"
_rate_lock = threading.Lock()
_rate_window: dict[str, list[float]] = {}

app = FastAPI(title="ImageTrace OSINT", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET","POST","DELETE"], allow_headers=["X-API-Key","Content-Type"])

def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def migrate():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS investigations (
            id TEXT PRIMARY KEY, created_at REAL NOT NULL, filename TEXT NOT NULL,
            sha256 TEXT NOT NULL, phash TEXT NOT NULL, metadata TEXT NOT NULL,
            image_path TEXT NOT NULL)""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_sha256 ON investigations(sha256)")

migrate()

def authorize(request: Request, x_api_key: str | None = Header(default=None)):
    key = os.getenv("APP_API_KEY", "")
    # Fail closed until operator sets a secret; never expose results publicly.
    if len(key) < 16:
        raise HTTPException(503, "APP_API_KEY must be set (at least 16 characters)")
    if not x_api_key or not secrets.compare_digest(key, x_api_key):
        raise HTTPException(401, "Unauthorized")
    if request.method == "POST":
        now = time.monotonic()
        identity = hashlib.sha256(x_api_key.encode()).hexdigest()
        with _rate_lock:
            history = [t for t in _rate_window.get(identity, []) if now-t < 60]
            if len(history) >= 20:
                raise HTTPException(429, "Too many processing requests; retry in one minute")
            history.append(now)
            _rate_window[identity] = history

def cleanup():
    limit = time.time() - max(1, RETENTION_HOURS) * 3600
    with connect() as db:
        rows = db.execute("SELECT id,image_path FROM investigations WHERE created_at < ?", (limit,)).fetchall()
        for row in rows:
            Path(row["image_path"]).unlink(missing_ok=True)
            db.execute("DELETE FROM investigations WHERE id=?", (row["id"],))

def get_item(item_id):
    with connect() as db:
        row = db.execute("SELECT * FROM investigations WHERE id=?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Investigation not found")
    return row

def analyze(data: bytes):
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File too large")
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ("JPEG", "PNG", "WEBP"):
            raise HTTPException(415, "Only JPEG, PNG, WEBP supported")
        if img.width * img.height > 35_000_000:
            raise HTTPException(413, "Too many pixels")
        exif = img.getexif()
        # Return safe subset; GPS intentionally omitted from results.
        fields = {271:"camera_make",272:"camera_model",306:"datetime",36867:"datetime_original",274:"orientation",305:"software"}
        metadata = {name:str(exif[tag])[:200] for tag,name in fields.items() if tag in exif}
        metadata.update({"width":img.width,"height":img.height,"format":img.format,"file_bytes":len(data),
                         "gps_present":bool(exif.get(34853)), "gps_disclosed":False})
        oriented = ImageOps.exif_transpose(img).convert("RGB")
        p_hash = str(imagehash.phash(oriented))
        # OCR is optional and never represented as complete or conclusive.
        try:
            import pytesseract
            text = pytesseract.image_to_string(oriented, timeout=4).strip()[:2000]
            metadata["ocr_text"] = text
            metadata["ocr_status"] = "processed"
        except Exception:
            metadata["ocr_status"] = "unavailable"
        return hashlib.sha256(data).hexdigest(), p_hash, metadata
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(415, "Invalid or unsupported image")

def serialize(row):
    return {"id":row["id"],"created_at":datetime.fromtimestamp(row["created_at"],timezone.utc).isoformat(),
            "filename":row["filename"],"sha256":row["sha256"],"phash":row["phash"],
            "metadata":json.loads(row["metadata"])}

def matches(item):
    with connect() as db:
        rows = db.execute("SELECT * FROM investigations WHERE id != ? ORDER BY created_at DESC LIMIT 500", (item["id"],)).fetchall()
    output = []
    for row in rows:
        distance = imagehash.hex_to_hash(item["phash"]) - imagehash.hex_to_hash(row["phash"])
        exact = row["sha256"] == item["sha256"]
        if exact or distance <= 10:
            output.append({"id":row["id"],"filename":row["filename"],"type":"exact" if exact else "visual_similarity",
              "phash_distance":distance,"similarity_note":"Hamming distance of 64-bit pHash (0 is identical); not a probability",
              "source":"private_local_index","verified":exact})
    return sorted(output,key=lambda m:(not m["verified"],m["phash_distance"]))

@app.get("/api/health")
def health():
    return {"status":"ok","mode":"local_index","external_search":"not_configured"}

@app.post("/api/analyze",dependencies=[Depends(authorize)])
async def upload(file:UploadFile=File(...)):
    cleanup()
    if file.content_type not in ("image/jpeg","image/png","image/webp"):
        raise HTTPException(415, "Invalid content type")
    data = await file.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES: raise HTTPException(413, "File too large")
    digest,phash,meta = analyze(data)
    ident = str(uuid.uuid4())
    path = DATA / (ident+".img")
    path.write_bytes(data)
    created = time.time()
    try:
        with connect() as db:
            db.execute("INSERT INTO investigations VALUES (?,?,?,?,?,?,?)",
                       (ident,created,Path(file.filename or "image").name[:120],digest,phash,json.dumps(meta),str(path)))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    item = get_item(ident)
    return {**serialize(item),"matches":matches(item),"external_results":[],
            "external_status":"not_configured","limitations":["pHash may miss crops","No web-wide image index"]}

@app.get("/api/investigations",dependencies=[Depends(authorize)])
def history():
    cleanup()
    with connect() as db:
        rows=db.execute("SELECT * FROM investigations ORDER BY created_at DESC LIMIT 100").fetchall()
    return [serialize(row) for row in rows]

@app.get("/api/investigations/{item_id}",dependencies=[Depends(authorize)])
def detail(item_id:str):
    cleanup()
    row=get_item(item_id)
    return {**serialize(row),"matches":matches(row),"external_results":[],"external_status":"not_configured"}

@app.get("/api/investigations/{item_id}/image",dependencies=[Depends(authorize)])
def image_bytes(item_id:str):
    row=get_item(item_id)
    return Response(Path(row["image_path"]).read_bytes(),media_type={"JPEG":"image/jpeg","PNG":"image/png","WEBP":"image/webp"}[json.loads(row["metadata"])["format"]],
                    headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})

@app.get("/api/investigations/{item_id}/report.json",dependencies=[Depends(authorize)])
def report_json(item_id:str):
    row=get_item(item_id)
    payload={**serialize(row),"local_matches":matches(row),"public_web_matches":[],
      "earliest_known_public_appearance":None,"external_provider_status":"not_configured",
      "finding_status":"local_hashes_verified; public_sources_unknown",
      "limitations":["Only user-uploaded private local index searched","No proof of manipulation or origin","No facial identification"]}
    return Response(json.dumps(payload,ensure_ascii=False,indent=2),media_type="application/json",
                    headers={"Content-Disposition":f'attachment; filename="imagetrace-{item_id}.json"',"Cache-Control":"no-store"})

@app.get("/api/investigations/{item_id}/report.pdf",dependencies=[Depends(authorize)])
def report_pdf(item_id:str):
    row=get_item(item_id); info=serialize(row); buf=io.BytesIO()
    pdf=canvas.Canvas(buf,pagesize=(595,842))
    pdf.setTitle("ImageTrace OSINT - forensic report")
    pdf.setFont("Helvetica-Bold",16);pdf.drawString(48,790,"ImageTrace OSINT | Report")
    pdf.setFont("Helvetica",10)
    lines=[f"ID: {info['id']}",f"Analyzed (UTC): {info['created_at']}",
           f"Filename: {info['filename'][:65]}",f"SHA-256: {info['sha256'][:50]}",f"       {info['sha256'][50:]}",
           f"pHash (64-bit): {info['phash']}",f"Dimensions: {info['metadata']['width']} x {info['metadata']['height']}",
           f"Local matching images: {len(matches(row))}",
           "Public web search: NOT CONFIGURED; no matches asserted.",
           "Earliest known public appearance: UNKNOWN.",
           "Interpretation: hashes verify file equality; pHash is heuristic.",
           "Limitations: cannot prove original source or image manipulation.",
           "Privacy: no facial identification; GPS coordinates suppressed."]
    y=765
    for line in lines:
        pdf.drawString(48,y,line);y-=23
    try:
        im=Image.open(row["image_path"]);im.thumbnail((440,310))
        pdf.drawImage(ImageReader(im.convert("RGB")),48,110,width=im.width*min(440/im.width,300/im.height),
                      height=im.height*min(440/im.width,300/im.height))
    except Exception: pass
    pdf.showPage();pdf.save()
    return Response(buf.getvalue(),media_type="application/pdf",
        headers={"Content-Disposition":f'attachment; filename="imagetrace-{item_id}.pdf"',"Cache-Control":"no-store"})

@app.delete("/api/investigations/{item_id}",dependencies=[Depends(authorize)])
def delete(item_id:str):
    row=get_item(item_id)
    with connect() as db: db.execute("DELETE FROM investigations WHERE id=?",(item_id,))
    Path(row["image_path"]).unlink(missing_ok=True)
    return {"deleted":True,"id":item_id}

@app.post("/api/compare",dependencies=[Depends(authorize)])
async def compare(first:UploadFile=File(...),second:UploadFile=File(...)):
    a=await first.read(MAX_BYTES+1);b=await second.read(MAX_BYTES+1)
    sha_a,p_a,meta_a=analyze(a);sha_b,p_b,meta_b=analyze(b)
    # Align dimensions for an orientative visual change map. Pixel ratio is not a tampering score.
    ia=ImageOps.exif_transpose(Image.open(io.BytesIO(a))).convert("RGB")
    ib=ImageOps.exif_transpose(Image.open(io.BytesIO(b))).convert("RGB")
    size=(min(768,max(ia.width,ib.width)), min(768,max(ia.height,ib.height)))
    ia=ImageOps.pad(ia,size,color=(0,0,0)); ib=ImageOps.pad(ib,size,color=(0,0,0))
    diff=ImageChops.difference(ia,ib)
    mask=diff.convert("L").point(lambda p: 255 if p > 30 else 0)
    mask_pixels=mask.histogram()
    altered=round(mask_pixels[255] / (size[0]*size[1]), 4)
    tint=Image.new("RGB",size,(255,72,90))
    heatmap=Image.composite(tint,ia,mask.point(lambda p: 125 if p else 0))
    out=io.BytesIO();heatmap.save(out,format="PNG")
    return {"pixel_change_fraction":altered,"pixel_method":"absolute grayscale difference > 30/255 after aspect-preserving padding; sensitive to alignment/compression",
            "difference_preview_png_base64":base64.b64encode(out.getvalue()).decode(),
            "exact":sha_a==sha_b,"sha256":[sha_a,sha_b],
            "phash":[p_a,p_b],"phash_distance":imagehash.hex_to_hash(p_a)-imagehash.hex_to_hash(p_b),
            "dimensions":[[meta_a["width"],meta_a["height"]],[meta_b["width"],meta_b["height"]]],
            "note":"Hamming distance, not forensic proof; cropping may change hashes."}

@app.post("/api/analyze-url",dependencies=[Depends(authorize)])
def analyze_url():
    # No SSRF surface until DNS pinning, size-bounded streaming and redirect rules are audited.
    raise HTTPException(501,"Remote URL ingestion disabled until SSRF-safe fetcher is available")
