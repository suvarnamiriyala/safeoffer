"""Text extraction from offer letters: PDF (pdfplumber / pypdf) and images (Tesseract OCR).

PyMuPDF is not installed in this environment, so pdfplumber/pypdf are used for text PDFs and
pdftoppm + Tesseract for scanned PDFs. Swap in PyMuPDF (fitz) later if you prefer.
"""
import os
import subprocess
import tempfile

MAX_OCR_PAGES = 3
OCR_LANG = os.environ.get("OCR_LANG", "eng+hin")  # set OCR_LANG=eng+hin+tel if tesseract-ocr-tel is installed


def _ocr_image(path):
    import pytesseract
    from PIL import Image
    img = Image.open(path)
    try:
        return pytesseract.image_to_string(img, lang=OCR_LANG)
    except Exception:
        return pytesseract.image_to_string(img)  # fall back to default language


def _pdf_text(path):
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages[:20])
    except Exception:
        try:
            from pypdf import PdfReader
            return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages[:20])
        except Exception:
            return ""


def _pdf_ocr(path):
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-r", "150", "-png", "-f", "1", "-l", str(MAX_OCR_PAGES), path,
                        os.path.join(d, "p")], check=False, timeout=60)
        out = []
        for name in sorted(os.listdir(d)):
            if name.endswith(".png"):
                out.append(_ocr_image(os.path.join(d, name)))
        return "\n".join(out)


def extract_text(path, filename=""):
    """Returns (text, method)."""
    name = (filename or path).lower()
    if name.endswith(".pdf"):
        text = _pdf_text(path)
        if len(text.strip()) >= 30:
            return text.strip(), "pdf-text"
        return _pdf_ocr(path).strip(), "pdf-ocr"
    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")):
        return _ocr_image(path).strip(), "image-ocr"
    if name.endswith((".txt", ".eml", ".md")):
        with open(path, "r", errors="ignore") as f:
            return f.read(), "text"
    raise ValueError("Unsupported file type. Upload a PDF, image (PNG/JPG) or .txt")
