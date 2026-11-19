"""ImageTrace OSINT: local image forensics; no face recognition or web scraping."""
import hashlib
import io
import json
import os
import secrets
import base64
import httpx
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
from reportlab.lib.utils import simpleSplit

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
        db.execute("""CREATE TABLE IF NOT EXISTS public_checks (
           investigation_id TEXT PRIMARY KEY, checked_at TEXT NOT NULL,
           status TEXT NOT NULL, results TEXT NOT NULL)""")

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
            db.execute("DELETE FROM public_checks WHERE investigation_id=?", (row["id"],))

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

def public_search_status(item_id):
    with connect() as db:
        row = db.execute("SELECT * FROM public_checks WHERE investigation_id=?", (item_id,)).fetchone()
    return {"external_results":json.loads(row["results"]) if row else [],
            "external_status":row["status"] if row else "not_checked",
            "external_checked_at":row["checked_at"] if row else None}

def matches(item):
    with connect() as db:
        rows = db.execute("SELECT * FROM investigations WHERE id != ? ORDER BY created_at DESC LIMIT 500", (item["id"],)).fetchall()
    output = []
    for row in rows:
        distance = int(imagehash.hex_to_hash(item["phash"]) - imagehash.hex_to_hash(row["phash"]))
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
    return {**serialize(item),"matches":matches(item),**public_search_status(ident),
            "limitations":["pHash may miss crops","No web-wide image index"]}

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
    return {**serialize(row),"matches":matches(row),**public_search_status(item_id)}

@app.get("/api/investigations/{item_id}/image",dependencies=[Depends(authorize)])
def image_bytes(item_id:str):
    row=get_item(item_id)
    return Response(Path(row["image_path"]).read_bytes(),media_type={"JPEG":"image/jpeg","PNG":"image/png","WEBP":"image/webp"}[json.loads(row["metadata"])["format"]],
                    headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})

@app.get("/api/investigations/{item_id}/report.json",dependencies=[Depends(authorize)])
def report_json(item_id:str):
    row=get_item(item_id)
    lookup=public_search_status(item_id)
    public_results=lookup["external_results"]
    payload={**serialize(row),"local_matches":matches(row),"public_web_matches":public_results,
      "earliest_known_public_appearance":None,"external_provider_status":lookup["external_status"],
      "external_checked_at":lookup["external_checked_at"],
      "finding_status":"local_hashes_verified; public provider exact SHA1 results when explicitly checked",
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
    public=public_search_status(item_id)
    lines=[f"ID: {info['id']}",f"Analyzed (UTC): {info['created_at']}",
           f"Filename: {info['filename'][:65]}",f"SHA-256: {info['sha256'][:50]}",f"       {info['sha256'][50:]}",
           f"pHash (64-bit): {info['phash']}",f"Dimensions: {info['metadata']['width']} x {info['metadata']['height']}",
           f"Local matching images: {len(matches(row))}",
           f"Wikimedia Commons exact SHA1 matches: {len(public['external_results'])}",
           f"External check status: {public['external_status']}",
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
    public_items=public["external_results"]
    if public_items:
        pdf.showPage()
        pdf.setFont("Helvetica-Bold",15)
        pdf.drawString(48,797,"Wikimedia Commons: exact SHA-1 file matches")
        y=763
        for i,match in enumerate(public_items,1):
            if y < 115:
                pdf.showPage();y=790
            pdf.setFont("Helvetica-Bold",10)
            for line in simpleSplit(f"{i}. {match.get('title','Untitled')}", "Helvetica-Bold",10,495):
                pdf.drawString(48,y,line);y-=15
            pdf.setFont("Helvetica",9)
            for line in simpleSplit(f"Source: {match.get('page_url','')}", "Helvetica",9,490):
                pdf.drawString(48,y,line);y-=14
            try:
                pdf.linkURL(match["page_url"],(48,y,545,y+32),relative=0)
            except Exception: pass
            pdf.drawString(48,y,f"Last uploaded: {match.get('published_at') or 'UNKNOWN'}; original appearance: UNKNOWN")
            y-=34
        if y < 90: pdf.showPage();y=790
        pdf.setFont("Helvetica",9)
        pdf.drawString(48,y,"Evidence: provider SHA-1 lookup; links require independent verification.")
    pdf.showPage();pdf.save()
    return Response(buf.getvalue(),media_type="application/pdf",
        headers={"Content-Disposition":f'attachment; filename="imagetrace-{item_id}.pdf"',"Cache-Control":"no-store"})

@app.delete("/api/investigations/{item_id}",dependencies=[Depends(authorize)])
def delete(item_id:str):
    row=get_item(item_id)
    with connect() as db: db.execute("DELETE FROM investigations WHERE id=?",(item_id,))
    Path(row["image_path"]).unlink(missing_ok=True)
    with connect() as db: db.execute("DELETE FROM public_checks WHERE investigation_id=?", (item_id,))
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
    # ORB keypoints with geometric verification: robust to some crops/rotations/scales.
    feature_matches=0;feature_inliers=0;possibly_same_scene=False
    try:
        import cv2
        import numpy as np
        gray_a=np.asarray(ImageOps.exif_transpose(Image.open(io.BytesIO(a))).convert("L"))
        gray_b=np.asarray(ImageOps.exif_transpose(Image.open(io.BytesIO(b))).convert("L"))
        orb=cv2.ORB_create(nfeatures=1400)
        kp_a,desc_a=orb.detectAndCompute(gray_a,None)
        kp_b,desc_b=orb.detectAndCompute(gray_b,None)
        if desc_a is not None and desc_b is not None:
            candidate=cv2.BFMatcher(cv2.NORM_HAMMING,crossCheck=True).match(desc_a,desc_b)
            good=[m for m in candidate if m.distance < 58]
            feature_matches=len(good)
            if feature_matches >= 8:
                src=np.float32([kp_a[m.queryIdx].pt for m in good]).reshape(-1,1,2)
                dst=np.float32([kp_b[m.trainIdx].pt for m in good]).reshape(-1,1,2)
                _,mask_h=cv2.findHomography(src,dst,cv2.RANSAC,5.0)
                if mask_h is not None:
                    feature_inliers=int(mask_h.sum())
                    possibly_same_scene=feature_inliers>=10 and feature_inliers/max(feature_matches,1)>=0.45
    except (ImportError,ValueError,cv2.error) if "cv2" in locals() else (ImportError,ValueError):
        pass
    return {"feature_matches":feature_matches,"feature_inliers":feature_inliers,
            "possibly_same_scene":possibly_same_scene,
            "feature_note":"ORB keypoint homography is an indicative visual match only; not identity or proof of editing",
            "pixel_change_fraction":altered,"pixel_method":"absolute grayscale difference > 30/255 after aspect-preserving padding; sensitive to alignment/compression",
            "difference_preview_png_base64":base64.b64encode(out.getvalue()).decode(),
            "exact":sha_a==sha_b,"sha256":[sha_a,sha_b],
            "phash":[p_a,p_b],"phash_distance":int(imagehash.hex_to_hash(p_a)-imagehash.hex_to_hash(p_b)),
            "dimensions":[[meta_a["width"],meta_a["height"]],[meta_b["width"],meta_b["height"]]],
            "note":"Hamming distance, not forensic proof; cropping may change hashes."}


@app.post("/api/investigations/{item_id}/search/commons",dependencies=[Depends(authorize)])
async def search_commons(item_id: str):
    """Opt-in exact-file SHA1 search in Wikimedia Commons. Sends hash only, not image."""
    cleanup()
    row=get_item(item_id)
    sha1=hashlib.sha1(Path(row["image_path"]).read_bytes()).hexdigest()
    params={"action":"query","list":"allimages","aisha1":sha1,
            "aiprop":"timestamp|url|sha1|size","format":"json","formatversion":"2","ailimit":"20"}
    ua="ImageTraceOSINTBot/0.1 (https://github.com/sebastisnzoth/reseaecheye; research tool)"
    try:
        async with httpx.AsyncClient(timeout=8,follow_redirects=False,
                                    headers={"User-Agent":ua,"Accept":"application/json"}) as client:
            response=await client.get("https://commons.wikimedia.org/w/api.php",params=params)
            response.raise_for_status()
            data=response.json()
        if "error" in data or not isinstance(data.get("query",{}).get("allimages"),list):
            raise ValueError("Provider returned an unexpected response")
    except (httpx.HTTPError,ValueError,TypeError) as exc:
        # Provider failure is not an empty match.
        return {"external_status":"provider_unavailable","external_results":[],
                "detail":"Wikimedia Commons query failed or was rate limited; no result asserted"}
    results=[]
    for image in data["query"]["allimages"][:20]:
        source=image.get("descriptionurl")
        url=image.get("url")
        if not isinstance(source,str) or not source.startswith("https://commons.wikimedia.org/"):
            continue
        if not isinstance(url,str) or not url.startswith("https://upload.wikimedia.org/"):
            continue
        results.append({"source":"Wikimedia Commons","domain":"commons.wikimedia.org",
                        "title":str(image.get("title",""))[:220],
                        "url":url,"page_url":source,
                        "published_at":image.get("timestamp"),"date_type":"last_file_upload",
                        "match_type":"exact_sha1","similarity":None,
                        "verification":"provider_sha1_lookup","thumbnail":url})
    checked_at=datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute("""INSERT INTO public_checks VALUES (?,?,?,?)
            ON CONFLICT(investigation_id) DO UPDATE SET
            checked_at=excluded.checked_at,status=excluded.status,results=excluded.results""",
            (item_id,checked_at,"checked",json.dumps(results)))
    return {"external_status":"checked","external_results":results,"external_checked_at":checked_at,
            "scope":"Only current file versions in Wikimedia Commons; SHA1 exact bytes; not whole web"}


@app.get("/api/investigations/{item_id}/reverse",dependencies=[Depends(authorize)])
def reverse_search(item_id: str):
    """Reverse search only the consenting operator's private upload index.
    Exact SHA-256 or pHash similarity, plus ORB geometry for cropped/resized copies.
    It is NOT an identity search and does not crawl other people's images.
    """
    cleanup()
    item = get_item(item_id)
    with connect() as db:
        candidates = db.execute(
          "SELECT * FROM investigations WHERE id != ? ORDER BY created_at DESC LIMIT 100",
          (item_id,)).fetchall()
    own_hash=imagehash.hex_to_hash(item["phash"])
    query_features=None
    try:
        import cv2
        import numpy as np
        with Image.open(item["image_path"]) as im:
            gray=np.asarray(ImageOps.exif_transpose(im).convert("L"))
        detector=cv2.ORB_create(nfeatures=1200)
        query_keypoints,query_features=detector.detectAndCompute(gray,None)
    except (ImportError,OSError,ValueError):
        query_features=None
    found=[]
    for candidate in candidates:
        exact=item["sha256"]==candidate["sha256"]
        distance=int(own_hash-imagehash.hex_to_hash(candidate["phash"]))
        inliers=0
        if not exact and distance>10 and query_features is not None:
            try:
                with Image.open(candidate["image_path"]) as im:
                    candidate_gray=np.asarray(ImageOps.exif_transpose(im).convert("L"))
                kp,desc=detector.detectAndCompute(candidate_gray,None)
                if desc is not None:
                    good=[m for m in cv2.BFMatcher(cv2.NORM_HAMMING,crossCheck=True).match(query_features,desc) if m.distance<58]
                    if len(good)>=10:
                        src=np.float32([query_keypoints[m.queryIdx].pt for m in good]).reshape(-1,1,2)
                        dst=np.float32([kp[m.trainIdx].pt for m in good]).reshape(-1,1,2)
                        _,inlier_mask=cv2.findHomography(src,dst,cv2.RANSAC,5.0)
                        if inlier_mask is not None:
                            n=int(inlier_mask.sum())
                            if n>=10 and n/len(good)>=0.45:inliers=n
            except (OSError,ValueError,cv2.error):
                pass
        if exact or distance<=10 or inliers>=10:
            found.append({
                "id":candidate["id"],
                "filename":candidate["filename"],
                "created_at":datetime.fromtimestamp(candidate["created_at"],timezone.utc).isoformat(),
                "match_type":"exact_bytes" if exact else "perceptual_similarity" if distance<=10 else "crop_or_scene_similarity",
                "verified_exact":exact,
                "phash_distance":distance,
                "orb_inliers":inliers,
                "source":"private_upload_index",
                "source_url":None,
                "explanation":"SHA-256 byte-identical" if exact else "64-bit pHash Hamming distance" if distance<=10 else "ORB geometric feature matching; not proof",
            })
    found.sort(key=lambda x:(not x["verified_exact"], x["match_type"]=="crop_or_scene_similarity", x["phash_distance"]))
    return {"investigation_id":item_id,"matches":found,"searched_records":len(candidates),
            "scope":"private_upload_index_only","no_public_identity_search":True,
            "external":public_search_status(item_id),
            "manual_providers":[
                {"name":"Google Lens","url":"https://lens.google.com/","automatic_upload":False},
                {"name":"TinEye","url":"https://tineye.com/","automatic_upload":False},
                {"name":"Bing Visual Search","url":"https://www.bing.com/visualsearch","automatic_upload":False}
            ],
            "limitations":["No whole-web reverse index","Perceptual and ORB matches are not source verification",
                          "Only up to 100 most recent local investigations searched"]}

@app.post("/api/analyze-url",dependencies=[Depends(authorize)])
def analyze_url():
    # No SSRF surface until DNS pinning, size-bounded streaming and redirect rules are audited.
    raise HTTPException(501,"Remote URL ingestion disabled until SSRF-safe fetcher is available")
