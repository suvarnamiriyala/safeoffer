"""Optional Gemini explanation / translation. Fails soft: without a key the app still works
using the built-in English / Hindi / Telugu text from i18n.py."""
import os

LANG_NAMES = {"en": "English", "hi": "Hindi", "te": "Telugu", "ta": "Tamil", "kn": "Kannada",
              "ml": "Malayalam", "mr": "Marathi", "bn": "Bengali", "gu": "Gujarati", "pa": "Punjabi",
              "or": "Odia", "as": "Assamese", "ur": "Urdu"}


def gemini_explain(result, lang="en"):
    """Returns a short plain-language explanation string, or None if Gemini is unavailable."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    flags = "\n".join(f"- {f['en']} (evidence: {f.get('evidence') or 'n/a'})" for f in result["flags"]) or "- none"
    prompt = (
        "You are SafeOffer, helping an Indian student or fresh graduate judge a job/internship offer.\n"
        f"Risk level computed by rules: {result['risk']['level'].upper()} (score {result['risk']['score']}/100).\n"
        f"Warning signs found:\n{flags}\n\n"
        f"Write 3-4 short sentences in {LANG_NAMES.get(lang, lang)}, simple words, no jargon, explaining what "
        "this means and the single most important thing to do next. Do not claim certainty; you are giving a "
        "risk estimate. Never tell the student the offer is definitely genuine."
    )
    try:
        import requests
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": key}, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return None
