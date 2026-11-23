"""Combines all checks into one result object used by the API."""
import i18n
import callcheck
from rules import (text_flags, email_flags, extract_entities, total_score, level_for, _f)
from verify import (company_checks, address_checks, google_lookup, maps_link, haversine_km,
                    OFFICIAL_LINKS)
from explain import gemini_explain


def _localize(flags, lang):
    for f in flags:
        f["title"] = i18n.pick(i18n.FLAG_TITLE, f["id"], lang) if lang != "en" else None
        if not f["title"]:
            f["title"] = f["en"]
    return flags


def _finish(flags, checks, lang, extra_links=None, overseas=False, extracted=None, info=None):
    flags.sort(key=lambda f: -f["weight"])
    score = total_score(flags)
    level = level_for(score, flags)
    steps = list(i18n.STEPS[level].get(lang) or i18n.STEPS[level]["en"])
    if overseas:
        steps.append(i18n.OVERSEAS_STEP.get(lang) or i18n.OVERSEAS_STEP["en"])
    result = {
        "risk": {"level": level, "score": score},
        "headline": i18n.HEADLINE[level].get(lang) or i18n.HEADLINE[level]["en"],
        "flags": _localize(flags, lang),
        "checks": checks,
        "next_steps": steps,
        "links": extra_links or [],
        "extracted": extracted or {},
        "info": info or {},
        "disclaimer": i18n.DISCLAIMER.get(lang) or i18n.DISCLAIMER["en"],
        "lang": lang,
    }
    result["ai_explanation"] = gemini_explain(result, lang)
    return result


def analyze_offer(p, lang="en"):
    text = (p.get("text") or "").strip()
    company = (p.get("company") or "").strip()
    ent = extract_entities(text)
    sender = (p.get("recruiter_email") or (ent["emails"][0] if ent["emails"] else "")).strip()
    cin = (p.get("cin") or ent["cin"]).strip()
    gstin = (p.get("gstin") or ent["gstin"]).strip()
    website = (p.get("website") or "").strip()

    flags = text_flags(text) if text else []
    checks = []

    ef, ec = email_flags(sender, company, website, text)
    flags += ef
    checks += ec

    cf, cc = company_checks(company, cin, gstin)
    flags += cf
    checks += cc

    af, ac, ainfo = address_checks(company, (p.get("registered_address") or "").strip(),
                                   (p.get("interview_address") or "").strip())
    flags += af
    checks += ac

    # Optional Google Maps Platform lookup (needs GOOGLE_MAPS_API_KEY; skipped otherwise)
    g_reg = google_lookup(company, p.get("registered_address", ""))
    if g_reg is not None:
        ainfo["google_registered"] = g_reg
        if g_reg.get("found") is False:
            flags.append(_f("address_not_found", "medium", 20,
                            "Google Maps finds no business at the registered address."))
            checks.append({"id": "maps", "label": "Google Maps", "status": "bad",
                           "detail": "No business found at this address."})
        elif g_reg.get("found"):
            checks.append({"id": "maps", "label": "Google Maps", "status": "ok",
                           "detail": f"Found: {g_reg.get('name')} - {g_reg.get('address')}. "
                                     "A listing does not prove the company is genuine."})
    else:
        checks.append({"id": "maps", "label": "Google Maps", "status": "unknown",
                       "detail": "Automatic Maps lookup is off (no API key). Use the map links below and check street view."})

    # Context answers from the student
    if p.get("applied") == "no":
        flags.append(_f("not_applied", "medium", 15, "You say you never applied to this company."))
    if p.get("had_interview") == "no":
        flags.append(_f("no_real_interview", "medium", 15,
                        "No video or in-person interview took place before the offer."))

    if not text and not any([company, sender, cin, gstin, p.get("registered_address"), p.get("interview_address")]):
        raise ValueError("Paste the offer text or fill in at least one detail.")

    overseas = any(f["id"] in {"overseas_hub_role", "overseas_hub", "overseas_generic", "visit_visa", "free_travel"}
                   for f in flags)
    links = []
    if company or p.get("registered_address"):
        links.append({"label": "Company address on Google Maps",
                      "url": maps_link(f"{company} {p.get('registered_address', '')}".strip())})
    if p.get("interview_address"):
        links.append({"label": "Interview location on Google Maps", "url": maps_link(p["interview_address"])})
    for k in ("mca", "gst"):
        links.append({"label": OFFICIAL_LINKS[k][0], "url": OFFICIAL_LINKS[k][1]})
    if overseas:
        links.append({"label": OFFICIAL_LINKS["emigrate"][0], "url": OFFICIAL_LINKS["emigrate"][1]})
    links.append({"label": OFFICIAL_LINKS["cyber"][0], "url": OFFICIAL_LINKS["cyber"][1]})

    return _finish(flags, checks, lang, links, overseas, ent, ainfo)


def analyze_call(answers, notes="", lang="en"):
    flags = callcheck.call_flags(answers or {})
    if notes.strip():
        flags += [f for f in text_flags(notes) if f["id"] not in {x["id"] for x in flags}]
    if not flags and not any(v is False for v in (answers or {}).values()) and not notes.strip():
        raise ValueError("Answer the questions first.")
    # map questionnaire ids to the shared flag-title translations where one exists
    qmap = {"q_money": "fee_request", "q_otp": "otp_pin", "q_abroad_visit": "overseas_hub",
            "q_secrecy": "secrecy", "q_urgency": "urgency", "q_no_interview": "no_interview",
            "q_high_pay": "high_pay", "q_messaging": "messaging_only"}
    qtext = {q["id"]: q["text"] for q in callcheck.questions(lang)}
    for f in flags:
        f["_q"] = f["id"]
    overseas = any(f["id"] in {"q_abroad_visit", "overseas_hub_role", "overseas_hub", "visit_visa"} for f in flags)
    result = _finish(flags, [], lang, [
        {"label": OFFICIAL_LINKS[k][0], "url": OFFICIAL_LINKS[k][1]}
        for k in (["emigrate"] if overseas else []) + ["mca", "gst", "cyber"]], overseas)
    for f in result["flags"]:
        if f.get("_q") in qtext:
            f["title"] = qtext[f["_q"]]
        f.pop("_q", None)
    return result
