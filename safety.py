"""Interview safety: live location sharing, arrival check-in and SOS.

Demo implementation - sessions live in memory and the trusted contact opens a tracking link
(no app install needed). `notify()` is the single place to plug in Firebase Cloud Messaging
or an SMS/WhatsApp gateway; right now it only logs.
"""
import time
import secrets
import threading

SESSIONS = {}
_LOCK = threading.Lock()


def notify(session, event_type, message):
    """Hook for FCM / SMS. Currently logs and records the event for the tracking page."""
    session["events"].append({"ts": time.time(), "type": event_type, "msg": message})
    print(f"[NOTIFY-STUB] to {session.get('contact_name') or 'contact'} "
          f"({session.get('contact_phone') or 'no phone'}): {message}")


def start(d):
    name = (d.get("name") or "Student").strip()[:60]
    sid = secrets.token_urlsafe(8)
    now = time.time()
    arrive_min = max(1, min(int(d.get("arrive_in_min") or 60), 24 * 60))
    s = {
        "id": sid, "name": name,
        "company": (d.get("company") or "")[:100],
        "address": (d.get("interview_address") or "")[:250],
        "contact_name": (d.get("contact_name") or "")[:60],
        "contact_phone": (d.get("contact_phone") or "")[:20],
        "phase": "travelling",
        "due": now + arrive_min * 60,
        "interview_min": max(10, min(int(d.get("interview_min") or 90), 8 * 60)),
        "started": now, "location": None, "trail": [], "sos_at": None, "events": [],
    }
    with _LOCK:
        SESSIONS[sid] = s
        notify(s, "started", f"{name} started sharing location for an interview"
                             f"{' at ' + s['company'] if s['company'] else ''}.")
    return sid


def _get(sid):
    s = SESSIONS.get(sid)
    if not s:
        raise KeyError("Unknown session")
    return s


def status(s):
    if s["sos_at"]:
        return "sos"
    if s["phase"] == "done":
        return "done"
    if time.time() > s["due"]:
        return "overdue"
    return "arrived" if s["phase"] == "at_interview" else "travelling"


def update_location(sid, lat, lng):
    lat, lng = float(lat), float(lng)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("Bad coordinates")
    with _LOCK:
        s = _get(sid)
        if s["phase"] == "done":
            return view(sid)
        s["location"] = {"lat": lat, "lng": lng, "ts": time.time()}
        s["trail"] = (s["trail"] + [[lat, lng]])[-60:]
    return view(sid)


def arrived(sid):
    with _LOCK:
        s = _get(sid)
        s["phase"] = "at_interview"
        s["due"] = time.time() + s["interview_min"] * 60
        notify(s, "arrived", f"{s['name']} has arrived. Next check-in due in {s['interview_min']} min.")
    return view(sid)


def safe(sid, stop=True):
    """Student confirms they are safe. stop=True ends sharing."""
    with _LOCK:
        s = _get(sid)
        if stop:
            s["phase"] = "done"
            notify(s, "safe", f"{s['name']} confirmed they are safe. Sharing stopped.")
        else:
            s["due"] = time.time() + 30 * 60
            notify(s, "safe", f"{s['name']} checked in: safe.")
    return view(sid)


def sos(sid):
    with _LOCK:
        s = _get(sid)
        s["sos_at"] = time.time()
        loc = s["location"]
        where = f" Last location: {loc['lat']:.5f},{loc['lng']:.5f}" if loc else ""
        notify(s, "sos", f"SOS from {s['name']}!{where}")
    return view(sid)


def view(sid):
    s = _get(sid)
    st = status(s)
    if st == "overdue" and not any(e["type"] == "overdue" for e in s["events"]):
        with _LOCK:
            notify(s, "overdue", f"{s['name']} missed the check-in. Try calling them now.")
    return {k: s[k] for k in ("id", "name", "company", "address", "contact_name", "phase",
                              "location", "trail", "events", "sos_at")} | {
        "status": st, "due_in_sec": int(s["due"] - time.time()), "server_time": time.time()}
