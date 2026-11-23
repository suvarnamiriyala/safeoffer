"""Company / address verification helpers.

What runs offline (always): CIN and GSTIN structure + GSTIN checksum, address comparison.
What needs a key + internet (optional): Google Places / Geocoding lookup.
MCA and GST databases have no free public API, so we validate the *format* and give the
official portal link for the final confirmation.
"""
import os
import re
import math
import datetime
from urllib.parse import quote_plus

from rules import _f

GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GST_STATE_CODES = set(range(1, 39)) | {97, 99}
PAN_ENTITY = {"P": "an individual / proprietor", "C": "a company", "F": "a firm / LLP", "H": "a HUF",
              "A": "an association", "T": "a trust", "B": "a body of individuals",
              "L": "a local authority", "J": "an artificial juridical person", "G": "a government body"}

OFFICIAL_LINKS = {
    "mca": ("MCA - Company Master Data (check status, directors, address)", "https://www.mca.gov.in"),
    "gst": ("GST portal - Search Taxpayer by GSTIN", "https://services.gst.gov.in/services/searchtp"),
    "emigrate": ("eMigrate - registered / illegal recruiting agents", "https://emigrate.gov.in"),
    "cyber": ("Report cyber fraud (or call 1930)", "https://cybercrime.gov.in"),
}


def parse_cin(cin):
    cin = (cin or "").strip().upper()
    if not cin:
        return None
    out = {"cin": cin, "valid": False, "issues": []}
    m = re.fullmatch(r"([LU])(\d{5})([A-Z]{2})(\d{4})([A-Z]{3})(\d{6})", cin)
    if not m:
        out["issues"].append("CIN must be 21 characters: L/U + 5 digits + 2-letter state + year + 3 letters + 6 digits.")
        return out
    year = int(m.group(4))
    now = datetime.date.today().year
    out.update(listed=m.group(1) == "L", industry=m.group(2), state=m.group(3), year=year,
               ownership=m.group(5), reg_no=m.group(6))
    if year < 1850 or year > now:
        out["issues"].append(f"Incorporation year {year} is impossible.")
        return out
    out["valid"] = True
    out["age_years"] = now - year
    return out


def gstin_checksum(g15):
    total = 0
    for i, ch in enumerate(g15[:14]):
        idx = GST_CHARS.index(ch)
        prod = idx * (1 if i % 2 == 0 else 2)
        total += prod // 36 + prod % 36
    return GST_CHARS[(36 - total % 36) % 36]


def validate_gstin(gstin):
    g = (gstin or "").strip().upper()
    if not g:
        return None
    out = {"gstin": g, "valid": False, "issues": []}
    if not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", g):
        out["issues"].append("GSTIN must be 15 characters: 2-digit state + PAN + entity + Z + check digit.")
        return out
    if int(g[:2]) not in GST_STATE_CODES:
        out["issues"].append(f"State code {g[:2]} does not exist.")
        return out
    if gstin_checksum(g) != g[14]:
        out["issues"].append("Check digit does not match - this GSTIN is mistyped or fabricated.")
        return out
    out["valid"] = True
    out["pan"] = g[2:12]
    out["entity_code"] = g[5]
    out["entity"] = PAN_ENTITY.get(g[5], "unknown")
    return out


def company_checks(company, cin, gstin):
    """Returns (flags, checks)."""
    flags, checks = [], []
    is_company_name = bool(re.search(r"\b(pvt|private|ltd|limited|llp|inc)\b", company or "", re.I))

    c = parse_cin(cin)
    if c:
        if not c["valid"]:
            flags.append(_f("cin_invalid", "high", 30, "CIN is not a valid format: " + " ".join(c["issues"]), cin))
            checks.append({"id": "cin", "label": "CIN", "status": "bad", "detail": " ".join(c["issues"])})
        else:
            age = c["age_years"]
            detail = (f"Well-formed. Registered in {c['state']} in {c['year']} (~{age} yr old). "
                      "Format only - confirm the company is Active on MCA.")
            if age <= 1:
                flags.append(_f("company_new", "medium", 25,
                                f"Company was incorporated only in {c['year']} - brand-new companies are a risk "
                                "when they offer many jobs or ask for money.", cin))
                checks.append({"id": "cin", "label": "CIN", "status": "warn", "detail": detail})
            else:
                checks.append({"id": "cin", "label": "CIN", "status": "ok", "detail": detail})
    elif is_company_name:
        checks.append({"id": "cin", "label": "CIN", "status": "unknown",
                       "detail": "No CIN provided. Ask the recruiter for it and check on MCA."})

    g = validate_gstin(gstin)
    if g:
        if not g["valid"]:
            flags.append(_f("gstin_invalid", "high", 30, "GSTIN is invalid: " + " ".join(g["issues"]), gstin))
            checks.append({"id": "gstin", "label": "GSTIN", "status": "bad", "detail": " ".join(g["issues"])})
        else:
            detail = f"Valid format and check digit. PAN inside it belongs to {g['entity']}."
            if is_company_name and g["entity_code"] not in ("C", "F", "A", "T", "B", "G", "L", "J"):
                flags.append(_f("gstin_entity_mismatch", "medium", 25,
                                f"Company name says Pvt Ltd / Ltd but the GSTIN is registered to {g['entity']}.",
                                gstin))
                checks.append({"id": "gstin", "label": "GSTIN", "status": "warn", "detail": detail})
            else:
                checks.append({"id": "gstin", "label": "GSTIN", "status": "ok",
                               "detail": detail + " Confirm the business name on the GST portal."})
    return flags, checks


# ---------------- addresses ----------------
STOP = {"the", "and", "road", "rd", "street", "st", "near", "opp", "opposite", "behind", "next", "floor",
        "plot", "no", "door", "main", "cross", "layout", "nagar", "colony", "india", "district", "dist",
        "mandal", "village", "pin", "pincode", "office", "building", "bldg", "complex", "tower", "towers"}
RESIDENTIAL = (r"flat\s*(no)?|apartment|apt\b|residence|residency|house\s*no|villa|room\s*no|\bpg\b|hostel|"
               r"my\s+(home|house)|\bhome\b")
PUBLIC_PLACE = (r"hotel|restaurant|cafe|café|lodge|guest\s*house|resort|bus\s*(stand|stop)|railway\s*station|"
                r"airport|food\s*court|mall|park\b|parking")


def _tokens(addr):
    return {w for w in re.findall(r"[a-z]{3,}", addr.lower()) if w not in STOP}


def _pincode(addr):
    m = re.search(r"(?<!\d)([1-9]\d{2})\s?(\d{3})(?!\d)", addr)
    return (m.group(1) + m.group(2)) if m else None


def maps_link(query):
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(query)


def address_checks(company, registered, interview):
    """Compare registered address with interview location. Returns (flags, checks, info)."""
    flags, checks, info = [], [], {}
    if registered:
        info["registered_maps"] = maps_link(f"{company} {registered}".strip())
    if interview:
        info["interview_maps"] = maps_link(interview)
        low = interview.lower()
        if re.search(PUBLIC_PLACE, low):
            flags.append(_f("address_public_place", "high", 30,
                            "Interview is at a hotel / cafe / public place instead of an office.",
                            re.search(PUBLIC_PLACE, low).group(0)))
            checks.append({"id": "interview_place", "label": "Interview place", "status": "bad",
                           "detail": "Hotel / cafe / public place. Genuine companies interview at their office or online."})
        elif re.search(RESIDENTIAL, low):
            flags.append(_f("address_residential", "medium", 20,
                            "Interview address looks like a residence / flat, not an office.",
                            re.search(RESIDENTIAL, low).group(0)))
            checks.append({"id": "interview_place", "label": "Interview place", "status": "warn",
                           "detail": "Looks residential. Check on street view that an office really exists."})

    if registered and interview:
        a, b = _tokens(registered), _tokens(interview)
        sim = len(a & b) / max(1, len(a | b))
        pa, pb = _pincode(registered), _pincode(interview)
        info["similarity"] = round(sim, 2)
        info["pincodes"] = [pa, pb]
        same = (pa and pb and pa == pb) or sim >= 0.45
        if pa and pb and pa != pb and sim < 0.45:
            flags.append(_f("address_mismatch", "medium", 25,
                            f"Interview location (PIN {pb}) is far from the company's registered address (PIN {pa}).",
                            f"{pa} vs {pb}"))
            checks.append({"id": "address", "label": "Registered vs interview address", "status": "bad",
                           "detail": f"Different areas (PIN {pa} vs {pb}). Ask the recruiter why."})
        elif not same:
            flags.append(_f("address_mismatch", "medium", 20,
                            "Interview location does not match the company's registered address.",
                            f"similarity {sim:.2f}"))
            checks.append({"id": "address", "label": "Registered vs interview address", "status": "warn",
                           "detail": f"Only {int(sim*100)}% of address words match. Could be a branch - confirm with the company."})
        else:
            checks.append({"id": "address", "label": "Registered vs interview address", "status": "ok",
                           "detail": "Addresses point to the same area."})
    elif interview and not registered:
        checks.append({"id": "address", "label": "Registered vs interview address", "status": "unknown",
                       "detail": "Add the registered address (from MCA / offer letter) to compare."})
    return flags, checks, info


# ---------------- optional Google Maps Platform lookup ----------------
def google_lookup(company, address):
    """Optional. Needs GOOGLE_MAPS_API_KEY and internet. Returns dict or None. Never raises."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key or not address:
        return None
    try:
        import requests
        r = requests.get("https://maps.googleapis.com/maps/api/place/textsearch/json",
                         params={"query": f"{company} {address}".strip(), "key": key}, timeout=10)
        data = r.json()
        res = (data.get("results") or [None])[0]
        if not res:
            return {"found": False, "status": data.get("status")}
        return {"found": True, "name": res.get("name"), "address": res.get("formatted_address"),
                "types": res.get("types"), "business_status": res.get("business_status"),
                "location": res.get("geometry", {}).get("location")}
    except Exception as e:  # network / key / quota problems must not break the app
        return {"error": str(e)[:120]}


def haversine_km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p = math.pi / 180
    h = (math.sin((la2 - la1) * p / 2) ** 2 +
         math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(h))
