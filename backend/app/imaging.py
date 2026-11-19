"""Image forensics, hashing, EXIF, OCR and visual comparison.

Everything in this module is computed locally from the pixels/bytes provided.
Signals are explicitly classified as verified facts, orientative inferences or
unknown information. Manipulation detection is NEVER presented as conclusive
proof, and no face/biometric analysis is performed anywhere in the project.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
from datetime import datetime
from io import BytesIO
from typing import Any

import cv2
import imagehash
import numpy as np
from PIL import ExifTags, Image

from .config import Settings

PHASH_BITS = 256  # hash_size=16 -> 16x16 DCT bits
EXACT_DISTANCE = 8
VISUAL_DISTANCE = 32
STOPWORDS = {
    "para", "con", "como", "desde", "este", "esta", "que", "los", "las", "una",
    "the", "and", "for", "with", "from", "this", "that", "image", "photo",
    "para", "com", "uma", "mais", "sem", "sob", "dos", "das", "não", "nao",
    "http", "https", "www", "com", "org", "2020", "2021", "2022", "2023",
    "2024", "2025", "2026", "copyright", "reserved", "todos", "direitos",
}


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def phash_hex(image: Image.Image) -> str:
    return str(imagehash.phash(image.convert("RGB"), hash_size=16))


def phash_distance(a: str | None, b: str | None) -> int | None:
    if not a or not b or len(a) != 64 or len(b) != 64:
        return None
    try:
        return int(imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b))
    except (ValueError, TypeError):
        return None


def similarity_from_distance(distance: int | None) -> float | None:
    if distance is None:
        return None
    return float(round(max(0.0, 100.0 * (1.0 - distance / PHASH_BITS)), 2))


def classify_distance(distance: int | None, sha_equal: bool = False) -> str:
    if sha_equal:
        return "exact"
    if distance is None:
        return "unknown"
    if distance <= EXACT_DISTANCE:
        return "near_duplicate"
    if distance <= VISUAL_DISTANCE:
        return "visual_similarity"
    return "unrelated"


def _dms_to_decimal(values: Any, ref: str) -> float | None:
    try:
        parts = [float(v) for v in values]
        if len(parts) != 3:
            return None
        decimal = parts[0] + parts[1] / 60 + parts[2] / 3600
        if str(ref).upper() in {"S", "W"}:
            decimal = -decimal
        return round(decimal, 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _exif_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S").isoformat(timespec="seconds")
    except ValueError:
        return None


def _run_exiftool(path: str) -> tuple[bool, dict[str, Any]]:
    binary = shutil.which("exiftool")
    if not binary:
        return False, {}
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            [binary, "-j", "-n", "-fast", "-charset", "filename=utf8", path],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if proc.returncode != 0:
            return False, {}
        parsed = json.loads(proc.stdout or "[]")
        data = parsed[0] if isinstance(parsed, list) and parsed else {}
        keep = {
            k: data[k]
            for k in (
                "FileName", "FileType", "MIMEType", "CreateDate", "ModifyDate",
                "DateTimeOriginal", "Make", "Model", "Software", "GPSLatitude",
                "GPSLongitude", "ImageWidth", "ImageHeight", "EncodingProcess",
            )
            if k in data
        }
        return True, keep
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return False, {}


def exif_analysis(
    image: Image.Image,
    *,
    allow_gps: bool,
    exiftool_path: str = "",
) -> dict[str, Any]:
    """Read EXIF. GPS is returned only when present AND explicitly authorized."""
    facts: list[dict[str, Any]] = []
    unknowns: list[str] = []
    inferences: list[dict[str, Any]] = []
    raw_exif = image.getexif()
    tags = {ExifTags.TAGS.get(k, k): v for k, v in raw_exif.items()}

    def add(key: str, value: Any, status: str = "fact", note: str = "") -> None:
        if value in (None, "", b"", []):
            return
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")[:300]
        elif isinstance(value, (dict, tuple, list)):
            value = str(value)[:300]
        facts.append({"field": key, "value": str(value)[:500], "status": status, "note": note})

    capture = _exif_date(tags.get("DateTimeOriginal") or tags.get("DateTimeDigitized") or tags.get("DateTime"))
    if capture:
        facts.append({
            "field": "capture_date",
            "value": capture,
            "status": "fact",
            "note": "Leído de EXIF; hora local de la cámara, zona horaria desconocida. No prueba cuándo se publicó la imagen.",
        })
    else:
        unknowns.append("Fecha de captura (sin etiqueta EXIF DateTimeOriginal/DateTime)")
    if tags.get("Make") or tags.get("Model"):
        facts.append({
            "field": "device",
            "value": f"{tags.get('Make', '')} {tags.get('Model', '')}".strip(),
            "status": "fact",
            "note": "Etiqueta EXIF declarada por el archivo; puede haber sido editada.",
        })
        facts.append({
            "field": "software",
            "value": str(tags.get("Software", "")),
            "status": "fact" if tags.get("Software") else "unknown",
            "note": "Software declarado en EXIF; su presencia sugiere reexportación pero no manipulación.",
        })
    else:
        unknowns.append("Marca y modelo de cámara/teléfono")
    add("orientation", tags.get("Orientation"))
    add("lens_model", tags.get("LensModel"))
    add("artist", tags.get("Artist"), note="Dato declarado en EXIF, no verificado externamente.")
    add("copyright", tags.get("Copyright"), note="Dato declarado en EXIF, no verificado externamente.")
    add("exposure_time", tags.get("ExposureTime"))
    add("iso", tags.get("ISOSpeedRatings"))

    gps_present = False
    gps_data: dict[str, Any] | None = None
    try:
        gps_ifd = raw_exif.get_ifd(ExifTags.IFD.GPSInfo)
    except (KeyError, AttributeError):
        gps_ifd = {}
    if gps_ifd:
        gps_present = True
        gps = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
        if allow_gps:
            lat = _dms_to_decimal(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef", "N"))
            lon = _dms_to_decimal(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef", "E"))
            if lat is not None and lon is not None:
                gps_data = {
                    "latitude": lat,
                    "longitude": lon,
                    "status": "fact",
                    "note": "Coordenadas declaradas en EXIF, autorizadas por el usuario. No verificadas contra fuentes externas.",
                }
            else:
                gps_data = {"status": "unknown", "note": "EXIF GPS presente pero no convertible."}
        else:
            gps_data = {
                "status": "withheld",
                "note": "La imagen contiene GPS, pero no se muestra: el usuario no autorizó su análisis.",
            }
    else:
        unknowns.append("Ubicación GPS (sin metadatos de geolocalización)")

    exiftool_available, exiftool_data = _run_exiftool(exiftool_path) if exiftool_path else (False, {})
    if not exiftool_available:
        unknowns.append("Metadatos avanzados de ExifTool (binario no instalado; se usó Pillow)")
    if tags.get("Software"):
        inferences.append({
            "field": "possible_reexport",
            "value": f"Software EXIF: {tags.get('Software')}",
            "status": "inference",
            "note": "Puede indicar que el archivo fue procesado o reexportado. No implica manipulación deliberada.",
        })

    return {
        "available": bool(tags),
        "facts": facts,
        "inferences": inferences,
        "unknowns": unknowns,
        "gps_present": gps_present,
        "gps": gps_data,
        "gps_authorized": bool(allow_gps),
        "exiftool_available": exiftool_available,
        "exiftool": exiftool_data,
        "disclaimer": "Los metadatos son declaraciones del archivo y pueden eliminarse o falsificarse; se reportan como hechos del archivo, no como hechos del mundo.",
    }


def scene_signals(image: Image.Image) -> dict[str, Any]:
    """Orientative photometric analysis. No object/face recognition is performed."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    gray = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    luminance = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    clipped_high = float(np.mean(luminance >= 250) * 100)
    clipped_low = float(np.mean(luminance <= 5) * 100)
    # Specular candidates: very bright, low-saturation compact regions.
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    spec = ((luminance > 235) & (sat < 0.18)).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(spec, connectivity=8)
    spec_regions = int(sum(1 for i in range(1, count) if 4 <= stats[i, cv2.CC_STAT_AREA] < 0.02 * spec.size))
    edges = cv2.Canny(gray, 80, 160)
    edge_density = float(np.mean(edges > 0) * 100)
    # Dominant colors (quantized), reported without semantic labels.
    small = cv2.resize(rgb.astype(np.uint8), (64, 64), interpolation=cv2.INTER_AREA)
    quantized = (small // 48 * 48).reshape(-1, 3)
    colors, counts = np.unique(quantized, axis=0, return_counts=True)
    order = np.argsort(counts)[::-1][:4]
    dominant = [
        {"rgb": [int(c) for c in colors[i]], "share_pct": round(float(counts[i] / len(quantized) * 100), 1)}
        for i in order
    ]
    return {
        "status": "inference",
        "brightness_mean": round(float(luminance.mean()), 2),
        "brightness_std": round(float(luminance.std()), 2),
        "clipped_highlights_pct": round(clipped_high, 2),
        "clipped_shadows_pct": round(clipped_low, 2),
        "specular_candidate_regions": spec_regions,
        "edge_density_pct": round(edge_density, 2),
        "dominant_colors": dominant,
        "notes": [
            "Estadísticas de iluminación calculadas sobre los píxeles: son inferencias orientativas, no peritaje.",
            "Las regiones especulares candidatas se detectan por brillo y baja saturación; pueden ser reflejos, luces o fondos claros.",
            "No se identifican objetos, personas ni categorías semánticas; no se usa reconocimiento facial.",
        ],
    }


def _ela_signals(image: Image.Image) -> dict[str, Any]:
    rgb = image.convert("RGB")
    buf = BytesIO()
    rgb.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    recompressed = np.asarray(Image.open(buf).convert("RGB"), dtype=np.int16)
    original = np.asarray(rgb, dtype=np.int16)
    if original.shape != recompressed.shape:
        recompressed = np.asarray(
            Image.fromarray(recompressed.astype(np.uint8)).resize((rgb.width, rgb.height)),
            dtype=np.int16,
        )
    diff = np.abs(original - recompressed).max(axis=2).astype(np.float32)
    h, w = diff.shape
    bh, bw = max(8, h // 16), max(8, w // 16)
    blocks: list[float] = []
    for y in range(0, h - bh + 1, bh):
        for x in range(0, w - bw + 1, bw):
            blocks.append(float(diff[y : y + bh, x : x + bw].mean()))
    if not blocks:
        blocks = [float(diff.mean())]
    arr = np.asarray(blocks)
    threshold = float(arr.mean() + 2 * arr.std())
    anomalous = float(np.mean(arr > threshold) * 100)
    return {
        "method": "Error Level Analysis (ELA) sobre recompresión JPEG calidad 90",
        "mean_error": round(float(diff.mean()), 3),
        "max_error": round(float(diff.max()), 3),
        "anomalous_block_pct": round(anomalous, 2),
        "score": round(min(100.0, anomalous * 4 + float(diff.mean()) * 2), 1),
    }


def compression_signals(image: Image.Image, fmt: str, original_bytes: bytes) -> dict[str, Any]:
    qtables = getattr(image, "quantization", None) or {}
    qtable_hash = hashlib.sha256(
        json.dumps({str(k): list(v) for k, v in qtables.items()}, sort_keys=True, default=str).encode()
    ).hexdigest()[:16] if qtables else None
    bpp = (len(original_bytes) * 8 / max(1, image.width * image.height))
    signals = []
    if fmt == "JPEG":
        signals.append(f"Tablas de cuantización JPEG presentes ({len(qtables)} tablas, huella {qtable_hash}).")
        if qtable_hash:
            signals.append("La huella de cuantización permite comparar versiones; no fecha ni autentica el archivo.")
    else:
        signals.append(f"Archivo {fmt}; ELA se calcula sobre una recompresión JPEG sintética y tiene valor limitado.")
    signals.append(f"Densidad de archivo: {bpp:.3f} bits por píxel (valores bajos sugieren compresión fuerte).")
    return {
        "status": "inference",
        "format": fmt,
        "bits_per_pixel": round(bpp, 3),
        "quantization_table_hash": qtable_hash,
        "signals": signals,
    }


def forensic_signals(image: Image.Image, original_bytes: bytes, fmt: str) -> dict[str, Any]:
    ela = _ela_signals(image)
    compression = compression_signals(image, fmt, original_bytes)
    gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    noise = cv2.Laplacian(gray, cv2.CV_32F)
    h, w = noise.shape
    bh, bw = max(8, h // 8), max(8, w // 8)
    tile_vars = [
        float(np.var(noise[y : y + bh, x : x + bw]))
        for y in range(0, h - bh + 1, bh)
        for x in range(0, w - bw + 1, bw)
    ]
    arr = np.asarray(tile_vars or [0.0])
    inconsistent = round(float(np.mean(np.abs(arr - arr.mean()) > 2 * arr.std()) * 100), 2)
    score = round(min(100.0, ela["score"] * 0.6 + inconsistent * 0.4), 1)
    return {
        "status": "orientative",
        "score": score,
        "ela": ela,
        "compression": compression,
        "noise_inconsistency_pct": inconsistent,
        "signals": [
            {
                "id": "ela",
                "label": "Niveles de error de recompresión (ELA)",
                "value": f"{ela['anomalous_block_pct']}% de bloques atípicos",
                "status": "inference",
            },
            {
                "id": "noise",
                "label": "Consistencia de ruido por regiones",
                "value": f"{inconsistent}% de regiones atípicas",
                "status": "inference",
            },
            {
                "id": "compression",
                "label": "Huella de compresión",
                "value": compression["quantization_table_hash"] or "no disponible",
                "status": "fact" if compression["quantization_table_hash"] else "unknown",
            },
        ],
        "disclaimer": (
            "Estas señales son orientativas y sensibles a recompresión, recorte, escalado y capturas de pantalla. "
            "NO constituyen prueba concluyente de manipulación ni peritaje judicial."
        ),
        "not_conclusive": True,
    }


def _ocr_with_rapidocr(image: Image.Image) -> dict[str, Any]:
    from rapidocr_onnxruntime import RapidOCR  # lazy: loads ONNX models

    engine = RapidOCR()
    result, _ = engine(np.asarray(image.convert("RGB")))
    lines = []
    for item in result or []:
        box, text, confidence = item[0], item[1], item[2]
        lines.append({
            "text": str(text).strip(),
            "confidence": round(float(confidence), 3),
            "box": [[float(p[0]), float(p[1])] for p in box],
        })
    return {"engine": "RapidOCR (ONNX Runtime, open source)", "lines": lines}


def _ocr_with_tesseract(image: Image.Image, cmd: str = "") -> dict[str, Any]:
    import pytesseract

    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    data = pytesseract.image_to_data(
        image.convert("RGB"), output_type=pytesseract.Output.DICT, config="--psm 11"
    )
    lines = []
    for i, text in enumerate(data.get("text", [])):
        clean = str(text).strip()
        if not clean:
            continue
        try:
            conf = float(data["conf"][i]) / 100.0
        except (ValueError, TypeError, KeyError):
            conf = 0.0
        lines.append({
            "text": clean,
            "confidence": round(conf, 3),
            "box": [
                [float(data["left"][i]), float(data["top"][i])],
                [float(data["left"][i] + data["width"][i]), float(data["top"][i] + data["height"][i])],
            ],
        })
    return {"engine": "Tesseract OCR", "lines": lines}


def ocr_analysis(image: Image.Image, settings: Settings) -> dict[str, Any]:
    """Extract visible text. Missing OCR engines produce an explicit 'unavailable'."""
    errors: list[str] = []
    if shutil.which("tesseract") or settings.tesseract_cmd:
        try:
            data = _ocr_with_tesseract(image, settings.tesseract_cmd)
            return _finalize_ocr(data)
        except Exception as exc:  # pragma: no cover - depends on host binaries
            errors.append(f"Tesseract: {type(exc).__name__}")
    try:
        data = _ocr_with_rapidocr(image)
        return _finalize_ocr(data)
    except Exception as exc:
        errors.append(f"RapidOCR: {type(exc).__name__}: {exc}")
    return {
        "status": "unavailable",
        "engine": None,
        "lines": [],
        "terms": [],
        "message": "No hay motor OCR disponible en este entorno. " + "; ".join(errors),
        "disclaimer": "No se inventa texto cuando el OCR falla o no está instalado.",
    }


def _finalize_ocr(data: dict[str, Any]) -> dict[str, Any]:
    lines = [line for line in data["lines"] if line["text"] and line["confidence"] >= 0.35]
    text = " ".join(line["text"] for line in lines)
    tokens = re.findall(r"[\wÀ-ÿ]{4,}", text.lower())
    terms: list[str] = []
    for token in tokens:
        if token not in STOPWORDS and token not in terms and not token.isdigit():
            terms.append(token)
        if len(terms) >= 8:
            break
    return {
        "status": "ok" if lines else "empty",
        "engine": data["engine"],
        "lines": lines[:60],
        "text": text[:2000],
        "terms": terms,
        "message": "Texto detectado localmente; puede contener errores. Verificar visualmente." if lines else "No se detectó texto visible.",
        "disclaimer": "El OCR es una inferencia sobre píxeles y no certifica el contenido ni la autenticidad del texto.",
    }


def _quantization_hash(image: Image.Image) -> str | None:
    qt = getattr(image, "quantization", None) or {}
    if not qt:
        return None
    return hashlib.sha256(
        json.dumps({str(k): list(v) for k, v in qt.items()}, sort_keys=True).encode()
    ).hexdigest()[:16]


def compare_images(
    image_a: Image.Image,
    bytes_a: bytes,
    image_b: Image.Image,
    bytes_b: bytes,
) -> tuple[dict[str, Any], bytes | None]:
    """Compare two images and build a difference heat-map."""
    sha_a, sha_b = bytes_sha256(bytes_a), bytes_sha256(bytes_b)
    hash_a, hash_b = phash_hex(image_a), phash_hex(image_b)
    distance = phash_distance(hash_a, hash_b)
    a_rgb = np.asarray(image_a.convert("RGB"))
    b_rgb = np.asarray(image_b.convert("RGB"))
    a_gray = cv2.cvtColor(a_rgb, cv2.COLOR_RGB2GRAY)
    resized = cv2.resize(b_rgb, (image_a.width, image_a.height), interpolation=cv2.INTER_AREA)
    diff = cv2.absdiff(a_rgb, resized)
    diff_gray = cv2.cvtColor(diff, cv2.COLOR_RGB2GRAY)
    changed_mask = (diff_gray > 24).astype(np.uint8) * 255
    changed_ratio = round(float(np.mean(diff_gray > 24) * 100), 2)
    mean_abs_error = round(float(diff_gray.mean()), 2)
    heat = cv2.applyColorMap(
        cv2.normalize(diff_gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8),
        cv2.COLORMAP_TURBO,
    )
    success, heat_bytes = cv2.imencode(".png", heat)
    heatmap = heat_bytes.tobytes() if success else None

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    cleaned = cv2.morphologyEx(changed_mask, cv2.MORPH_CLOSE, kernel)
    count, _, stats, _ = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
    min_area = max(64, (a_gray.size // 2000))
    regions = []
    for i in range(1, count):
        x, y, w, h, area = [int(stats[i, j]) for j in range(5)]
        if area >= min_area:
            regions.append({"x": x, "y": y, "width": w, "height": h, "area_px": area})
    regions = sorted(regions, key=lambda r: r["area_px"], reverse=True)[:12]

    crop: dict[str, Any] = {"status": "unknown", "note": "No se pudo estimar una transformación de recorte."}
    scale: float | None = None
    if b_rgb.shape[0] < a_gray.shape[0] and b_rgb.shape[1] < a_gray.shape[1]:
        b_gray = cv2.cvtColor(b_rgb, cv2.COLOR_RGB2GRAY)
        try:
            result = cv2.matchTemplate(a_gray, b_gray, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val >= 0.75:
                crop = {
                    "status": "detected",
                    "method": "Template matching (TM_CCOEFF_NORMED)",
                    "confidence": round(float(max_val), 3),
                    "offset": [int(max_loc[0]), int(max_loc[1])],
                    "candidate_size": [int(b_rgb.shape[1]), int(b_rgb.shape[0])],
                    "note": "La imagen B parece un recorte de A en la posición estimada. Inferencia, no prueba.",
                }
                scale = round(float(a_gray.shape[1] / b_rgb.shape[1]), 3)
        except cv2.error:
            pass
    if crop["status"] == "unknown":
        try:
            orb = cv2.ORB_create(nfeatures=1200)
            kp1, des1 = orb.detectAndCompute(a_gray, None)
            b_gray_full = cv2.cvtColor(b_rgb, cv2.COLOR_RGB2GRAY)
            kp2, des2 = orb.detectAndCompute(b_gray_full, None)
            if des1 is not None and des2 is not None and len(kp1) >= 8 and len(kp2) >= 8:
                matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
                knn = matcher.knnMatch(des2, des1, k=2)
                good = [m for m, n in knn if m.distance < 0.75 * n.distance]
                if len(good) >= 8:
                    src = np.float32([kp2[m.queryIdx].pt for m in good])
                    dst = np.float32([kp1[m.trainIdx].pt for m in good])
                    matrix, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC)
                    if matrix is not None:
                        sx = float(math.hypot(matrix[0, 0], matrix[1, 0]))
                        scale = round(sx, 3)
                        crop = {
                            "status": "estimated",
                            "method": "ORB + RANSAC (estimación afín parcial)",
                            "inliers": int(np.sum(inliers)) if inliers is not None else len(good),
                            "scale": sx,
                            "translation": [round(float(matrix[0, 2]), 1), round(float(matrix[1, 2]), 1)],
                            "note": "Transformación estimada entre versiones; puede corresponder a recorte, escalado o reencuadre.",
                        }
        except cv2.error:
            pass

    size_change = None
    if image_a.size != image_b.size:
        size_change = {
            "from": [image_a.width, image_a.height],
            "to": [image_b.width, image_b.height],
            "area_ratio": round(
                (image_b.width * image_b.height) / max(1, image_a.width * image_a.height), 3
            ),
        }
    q_a, q_b = _quantization_hash(image_a), _quantization_hash(image_b)
    alignment = alignment_assessment(image_a, image_b)
    classification = classify_distance(distance, sha_a == sha_b)
    if alignment.get("status") == "aligned" and classification == "unrelated":
        classification = "visual_similarity"
    result = {
        "sha256": {"a": sha_a, "b": sha_b, "equal": sha_a == sha_b},
        "phash": {
            "a": hash_a,
            "b": hash_b,
            "distance": distance,
            "bits": PHASH_BITS,
            "similarity_pct": similarity_from_distance(distance),
            "metric": "similitud = 100 × (1 − distancia Hamming / 256) sobre pHash DCT 16×16; no es probabilidad de autenticidad.",
        },
        "dimensions": {
            "a": [image_a.width, image_a.height],
            "b": [image_b.width, image_b.height],
            "size_change": size_change,
        },
        "pixels": {
            "changed_pct": changed_ratio,
            "mean_absolute_error": mean_abs_error,
            "changed_regions": regions,
            "method": "Diferencia absoluta por canal tras redimensionar B a A; píxel cambiado si diferencia > 24/255.",
        },
        "crop_detection": crop,
        "scale_estimate": scale,
        "compression": {
            "a": q_a,
            "b": q_b,
            "quantization_equal": (q_a == q_b) if (q_a and q_b) else None,
            "note": "Huellas de tablas JPEG distintas sugieren recompresión o reexportación; iguales no prueban origen común.",
        },
        "alignment": alignment,
        "crop_aware_similarity_pct": alignment.get("aligned_similarity_pct"),
        "classification": classification,
        "disclaimer": (
            "La comparación detecta diferencias de píxeles y similitud perceptual; no determina autoría ni manipulación deliberada. "
            "El pHash directo NO es invariante a recortes: para versiones recortadas se usa también alineación ORB/RANSAC sobre la región superpuesta."
        ),
    }
    return result, heatmap


def _resize_for_alignment(image: Image.Image, max_side: int = 900) -> Image.Image:
    scale = min(1.0, max_side / max(image.width, image.height))
    if scale == 1.0:
        return image.convert("RGB")
    return image.convert("RGB").resize(
        (max(32, int(image.width * scale)), max(32, int(image.height * scale))),
        Image.Resampling.LANCZOS,
    )


def _masked_rgb(array: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Replace non-overlapping pixels with the mean colour of the overlap."""
    valid = mask > 0
    if not valid.any():
        return array
    mean = array[valid].mean(axis=0).astype(np.uint8)
    result = array.copy()
    result[~valid] = mean
    return result


def alignment_assessment(image_a: Image.Image, image_b: Image.Image) -> dict[str, Any]:
    """Crop/scale-aware similarity using ORB + RANSAC and template matching.

    Plain pHash is NOT invariant to cropping. This function aligns B into A's
    coordinate space, compares only the overlapping region and reports an
    explicit method, coverage and confidence. It never claims identity.
    """
    a_img = _resize_for_alignment(image_a)
    b_img = _resize_for_alignment(image_b)
    a = np.asarray(a_img)
    b = np.asarray(b_img)
    ah, aw = a.shape[:2]
    bh, bw = b.shape[:2]
    a_gray = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
    b_gray = cv2.cvtColor(b, cv2.COLOR_RGB2GRAY)
    result: dict[str, Any] = {
        "status": "no_alignment",
        "method": None,
        "coverage": 0.0,
        "aligned_phash_distance": None,
        "aligned_similarity_pct": None,
        "mean_absolute_error": None,
        "inliers": 0,
        "note": "No se encontró una alineación geométrica fiable; no se declara similitud por recorte.",
    }

    def evaluate(warped: np.ndarray, mask: np.ndarray, method: str, inliers: int, confidence: float) -> dict[str, Any]:
        valid = mask > 0
        coverage = round(float(valid.sum() / max(1, ah * aw)), 3)
        if coverage < 0.25:
            result.update({
                "status": "low_coverage", "method": method, "coverage": coverage, "inliers": inliers,
                "note": "La superposición alineada es demasiado pequeña para declarar similitud.",
            })
            return result
        x, y, w, h = cv2.boundingRect(mask)
        a_crop = a[y : y + h, x : x + w]
        b_crop = warped[y : y + h, x : x + w]
        m_crop = mask[y : y + h, x : x + w]
        a_masked = _masked_rgb(a_crop, m_crop)
        b_masked = _masked_rgb(b_crop, m_crop)
        distance = phash_distance(phash_hex(Image.fromarray(a_masked)), phash_hex(Image.fromarray(b_masked)))
        mae = float(cv2.absdiff(a_masked, b_masked)[m_crop > 0].mean())
        distance_for_metric = distance if distance is not None else PHASH_BITS
        similarity = float(round(
            100.0 * (0.5 * (1.0 - distance_for_metric / PHASH_BITS) + 0.5 * (1.0 - min(mae, 255) / 255)),
            2,
        ))
        aligned = (
            distance is not None
            and distance <= 64
            and mae <= 70
            and inliers >= 8
            and coverage >= 0.30
            and confidence >= 0.35
        )
        result.update({
            "status": "aligned" if aligned else "below_threshold",
            "method": method,
            "coverage": coverage,
            "aligned_phash_distance": distance,
            "aligned_similarity_pct": similarity,
            "mean_absolute_error": round(mae, 2),
            "inliers": inliers,
            "confidence": float(round(float(confidence), 3)),
            "scale": float(round(float(np.hypot(matrix[0, 0], matrix[1, 0])), 3)) if matrix is not None else None,
            "note": (
                "Alineación verificada localmente sobre la región superpuesta: probable versión recortada o reescalada. "
                "La similitud se calcula tras alinear, no con el pHash directo."
                if aligned else
                "Se estimó una alineación, pero la similitud no supera los umbrales; no se declara coincidencia."
            ),
        })
        return result

    matrix: np.ndarray | None = None
    try:
        orb = cv2.ORB_create(nfeatures=1800)
        kp_a, des_a = orb.detectAndCompute(a_gray, None)
        kp_b, des_b = orb.detectAndCompute(b_gray, None)
        if des_a is not None and des_b is not None and len(kp_a) >= 8 and len(kp_b) >= 8:
            matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des_b, des_a, k=2)
            good = [m for m, n in matches if m.distance < 0.72 * n.distance]
            if len(good) >= 8:
                src = np.float32([kp_b[m.queryIdx].pt for m in good]).reshape(-1, 2)
                dst = np.float32([kp_a[m.trainIdx].pt for m in good]).reshape(-1, 2)
                matrix, inliers_mask = cv2.estimateAffinePartial2D(
                    src, dst, method=cv2.RANSAC, ransacReprojThreshold=4.0
                )
                if matrix is not None:
                    inliers = int(np.sum(inliers_mask)) if inliers_mask is not None else len(good)
                    warped = cv2.warpAffine(b, matrix, (aw, ah), flags=cv2.INTER_LINEAR)
                    valid = cv2.warpAffine(
                        np.full((bh, bw), 255, dtype=np.uint8), matrix, (aw, ah),
                        flags=cv2.INTER_NEAREST, borderValue=0,
                    )
                    return evaluate(
                        warped, valid, "ORB + RANSAC (affine alignment)", inliers,
                        inliers / max(1, len(good)),
                    )
    except cv2.error:
        pass

    # Fallback for low-texture images: direct template matching when B is smaller.
    if bh <= ah and bw <= aw and min(bh, bw) >= 16:
        try:
            scores = cv2.matchTemplate(a_gray, b_gray, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(scores)
            if max_val >= 0.72:
                matrix = np.array(
                    [[1.0, 0.0, float(max_loc[0])], [0.0, 1.0, float(max_loc[1])]], dtype=np.float32
                )
                warped = np.zeros_like(a)
                warped[max_loc[1] : max_loc[1] + bh, max_loc[0] : max_loc[0] + bw] = b
                valid = np.zeros((ah, aw), dtype=np.uint8)
                valid[max_loc[1] : max_loc[1] + bh, max_loc[0] : max_loc[0] + bw] = 255
                return evaluate(
                    warped, valid, "Template matching (TM_CCOEFF_NORMED)", 8, float(max_val)
                )
        except cv2.error:
            pass
    return result


def candidate_verification(
    query_image: Image.Image,
    query_sha256: str,
    query_phash: str,
    candidate_bytes: bytes,
) -> dict[str, Any] | None:
    """Verify a downloaded provider candidate against the query image."""
    from .security import ValidationError, sanitize_image

    try:
        candidate = sanitize_image(candidate_bytes, max_bytes=10 * 1024 * 1024)
    except ValidationError:
        return None
    sha = bytes_sha256(candidate_bytes)
    ph = phash_hex(candidate.image)
    direct_distance = phash_distance(query_phash, ph)
    classification = classify_distance(direct_distance, sha == query_sha256)
    alignment: dict[str, Any] = {"status": "not_needed"}
    similarity = similarity_from_distance(direct_distance)
    if classification in {"unrelated", "unknown"}:
        alignment = alignment_assessment(candidate.image, _query_as_image(query_image))
        if alignment.get("status") == "aligned":
            classification = "visual_similarity"
            similarity = alignment.get("aligned_similarity_pct")
    return {
        "sha256": sha,
        "sha256_equal": sha == query_sha256,
        "phash": ph,
        "phash_distance": direct_distance,
        "direct_phash_distance": direct_distance,
        "similarity_pct": similarity,
        "classification": classification,
        "alignment_verified": alignment.get("status") == "aligned",
        "alignment": alignment,
        "width": candidate.width,
        "height": candidate.height,
    }


def _query_as_image(image: Image.Image) -> Image.Image:
    return image.convert("RGB")
