"""SafeOffer API (Starlette - the framework FastAPI is built on).

Run:  uvicorn app:app --port 8000     then open http://localhost:8000
"""
import os
import tempfile
from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse
from starlette.routing import Route

import analyzer
import callcheck
import extract
import safety
import i18n

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_UPLOAD = 8 * 1024 * 1024


def ok(data, status=200):
    return JSONResponse(data, status_code=status)


def err(msg, status=400):
    return JSONResponse({"error": msg}, status_code=status)


async def body(request):
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def index(request):
    return FileResponse(os.path.join(HERE, "static", "index.html"))


async def track_page(request):
    return FileResponse(os.path.join(HERE, "static", "track.html"))


async def health(request):
    return ok({"ok": True,
               "gemini": bool(os.environ.get("GEMINI_API_KEY")),
               "google_maps": bool(os.environ.get("GOOGLE_MAPS_API_KEY")),
               "languages": i18n.LANGS})


async def api_extract(request):
    """Raw file bytes in the body, original name in the X-Filename header."""
    name = request.headers.get("x-filename", "upload.bin")
    raw = await request.body()
    if not raw:
        return err("Empty file")
    if len(raw) > MAX_UPLOAD:
        return err("File too large (max 8 MB)", 413)
    suffix = os.path.splitext(name)[1].lower() or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(raw)
        path = f.name
    try:
        text, method = extract.extract_text(path, name)
    except ValueError as e:
        return err(str(e), 415)
    except Exception as e:
        return err(f"Could not read file: {str(e)[:120]}", 422)
    finally:
        os.unlink(path)
    if not text.strip():
        return err("No text found in the file. Try a clearer photo or paste the text.", 422)
    return ok({"text": text, "method": method})


async def api_analyze(request):
    d = await body(request)
    try:
        return ok(analyzer.analyze_offer(d, d.get("lang", "en")))
    except ValueError as e:
        return err(str(e))


async def api_questions(request):
    return ok({"questions": callcheck.questions(request.query_params.get("lang", "en"))})


async def api_callcheck(request):
    d = await body(request)
    try:
        return ok(analyzer.analyze_call(d.get("answers") or {}, d.get("notes") or "", d.get("lang", "en")))
    except ValueError as e:
        return err(str(e))


# ---- safety ----
async def s_start(request):
    d = await body(request)
    try:
        sid = safety.start(d)
    except (ValueError, TypeError):
        return err("Invalid input")
    return ok({"id": sid, "tracker_path": f"/track/{sid}", "state": safety.view(sid)})


def _safety_route(fn):
    async def handler(request):
        sid = request.path_params["sid"]
        d = await body(request)
        try:
            return ok(fn(sid, d))
        except KeyError:
            return err("Unknown session", 404)
        except (ValueError, TypeError, KeyError):
            return err("Invalid input")
    return handler


s_loc = _safety_route(lambda sid, d: safety.update_location(sid, d.get("lat"), d.get("lng")))
s_arrived = _safety_route(lambda sid, d: safety.arrived(sid))
s_safe = _safety_route(lambda sid, d: safety.safe(sid, d.get("stop", True)))
s_sos = _safety_route(lambda sid, d: safety.sos(sid))


async def s_view(request):
    try:
        return ok(safety.view(request.path_params["sid"]))
    except KeyError:
        return err("Unknown session", 404)


app = Starlette(routes=[
    Route("/", index),
    Route("/track/{sid}", track_page),
    Route("/api/health", health),
    Route("/api/extract", api_extract, methods=["POST"]),
    Route("/api/analyze", api_analyze, methods=["POST"]),
    Route("/api/questions", api_questions),
    Route("/api/callcheck", api_callcheck, methods=["POST"]),
    Route("/api/safety/start", s_start, methods=["POST"]),
    Route("/api/safety/{sid}", s_view),
    Route("/api/safety/{sid}/location", s_loc, methods=["POST"]),
    Route("/api/safety/{sid}/arrived", s_arrived, methods=["POST"]),
    Route("/api/safety/{sid}/safe", s_safe, methods=["POST"]),
    Route("/api/safety/{sid}/sos", s_sos, methods=["POST"]),
])
