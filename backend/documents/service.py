"""Secure, local-first document extraction helpers.

OCR is an aid to data entry, never proof of authenticity or eligibility.
Optional dependencies are imported only when their processing path is used.
"""
from __future__ import annotations
import hashlib, io, json, re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}

class DocumentError(ValueError):
    pass

@dataclass
class Extraction:
    text: str
    method: str
    status: str
    confidence: float | None
    page_count: int
    warnings: list[str]


def detect_type(data: bytes) -> str:
    if data.startswith(b"%PDF-"): return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"): return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png"
    raise DocumentError("Unsupported or invalid file content. Upload a PDF, JPG or PNG.")


def validate_upload(filename: str, data: bytes) -> tuple[str, str]:
    if not data: raise DocumentError("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES: raise DocumentError("File exceeds the 20 MB upload limit.")
    mime = detect_type(data)
    ext = Path(filename or "document").suffix.lower()
    if ext != ALLOWED[mime]: raise DocumentError("File extension does not match its actual content.")
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)[:120] or "document" + ALLOWED[mime]
    return mime, safe_name


def _ocr_image(image) -> tuple[str, float | None, str, list[str]]:
    warnings = []
    try:
        import pytesseract
        from pytesseract import Output
        d = pytesseract.image_to_data(image, output_type=Output.DICT)
        words, scores = [], []
        for word, conf in zip(d.get("text", []), d.get("conf", [])):
            word = (word or "").strip()
            try: score = float(conf)
            except (TypeError, ValueError): score = -1
            if word and score >= 0:
                words.append(word); scores.append(score)
        text = " ".join(words)
        confidence = round(sum(scores) / len(scores) / 100, 3) if scores else None
        return text, confidence, "tesseract", warnings
    except Exception as exc:
        warnings.append(f"Tesseract OCR unavailable or failed: {type(exc).__name__}")
    try:
        from paddleocr import PaddleOCR
        import numpy as np
        ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        result = ocr.ocr(np.array(image), cls=True)
        lines, scores = [], []
        for page in result or []:
            for item in page or []:
                if item and len(item) > 1:
                    lines.append(str(item[1][0])); scores.append(float(item[1][1]))
        return "\n".join(lines), (round(sum(scores)/len(scores), 3) if scores else None), "paddleocr", warnings
    except Exception as exc:
        warnings.append(f"PaddleOCR unavailable or failed: {type(exc).__name__}")
        return "", None, "unavailable", warnings


def extract_document(data: bytes, mime: str) -> Extraction:
    warnings: list[str] = []
    if mime == "application/pdf":
        try:
            import fitz
            pdf = fitz.open(stream=data, filetype="pdf")
            page_text = [p.get_text("text").strip() for p in pdf]
            text = "\n\n".join(x for x in page_text if x)
            if text.strip():
                return Extraction(text, "pymupdf", "extracted", None, len(pdf), warnings)
            # Scanned PDF: render pages and OCR locally.
            try:
                from PIL import Image
                chunks, confidences, methods = [], [], []
                for page in pdf:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    t, c, m, w = _ocr_image(img); warnings.extend(w)
                    if t: chunks.append(t)
                    if c is not None: confidences.append(c)
                    methods.append(m)
                method = next((m for m in methods if m != "unavailable"), "unavailable")
                combined = "\n\n".join(chunks)
                status = "extracted" if combined.strip() else "needs_manual_review"
                confidence = round(sum(confidences)/len(confidences), 3) if confidences else None
                if not combined: warnings.append("No readable text was extracted; enter the required information manually.")
                return Extraction(combined, method, status, confidence, len(pdf), warnings)
            except Exception as exc:
                warnings.append(f"Scanned-PDF OCR could not run: {type(exc).__name__}")
                return Extraction("", "unavailable", "needs_manual_review", None, len(pdf), warnings)
        except Exception as exc:
            raise DocumentError(f"PDF could not be opened: {type(exc).__name__}") from exc
    try:
        from PIL import Image
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:
        raise DocumentError("Image could not be opened.") from exc
    text, confidence, method, warnings = _ocr_image(image)
    return Extraction(text, method, "extracted" if text.strip() else "needs_manual_review", confidence, 1, warnings)


def compare_extracted_fields(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag conflicting user-reviewed field values; never decides which is true."""
    values: dict[str, list[dict[str, str]]] = {}
    for doc in documents:
        fields = doc.get("corrected_fields") or doc.get("extracted_fields") or {}
        for key, value in fields.items():
            if value is None or str(value).strip() == "": continue
            values.setdefault(str(key), []).append({"document_id": str(doc.get("document_id", "")), "value": str(value).strip()})
    conflicts = []
    for field, entries in values.items():
        distinct = {x["value"].casefold() for x in entries}
        if len(distinct) > 1:
            conflicts.append({"field": field, "values": entries, "status": "requires_student_review",
                              "message": "Documents contain different values. Review the originals; no value has been selected automatically."})
    return conflicts


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
