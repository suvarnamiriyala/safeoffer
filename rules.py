"""Rule-based scam detection for job / internship offers.

Pure Python, no network. Every rule returns a flag dict:
    {id, severity, weight, en, evidence}
The same flag ids are translated in i18n.py.
"""
import re
from urllib.parse import urlparse

FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.in", "yahoo.co.in", "ymail.com",
    "outlook.com", "hotmail.com", "live.com", "msn.com", "rediffmail.com", "rediff.com",
    "aol.com", "icloud.com", "me.com", "proton.me", "protonmail.com", "mail.com",
    "zoho.in", "zohomail.com", "gmx.com", "yandex.com",
}

MULTI_TLDS = {"co.in", "ac.in", "org.in", "net.in", "gov.in", "nic.in", "edu.in",
              "res.in", "co.uk", "com.au", "com.sg"}

# Brands that scammers commonly impersonate -> their real email/website domains.
BRAND_DOMAINS = {
    "tcs": ["tcs.com"], "tata consultancy": ["tcs.com"],
    "infosys": ["infosys.com"], "wipro": ["wipro.com"],
    "cognizant": ["cognizant.com"], "hcl": ["hcltech.com", "hcl.com"],
    "tech mahindra": ["techmahindra.com"], "accenture": ["accenture.com"],
    "ibm": ["ibm.com"], "amazon": ["amazon.com", "amazon.in", "amazon.jobs"],
    "google": ["google.com"], "microsoft": ["microsoft.com"],
    "flipkart": ["flipkart.com"], "capgemini": ["capgemini.com"],
    "deloitte": ["deloitte.com"], "zoho": ["zohocorp.com", "zoho.com"],
    "hdfc": ["hdfcbank.com", "hdfcbank.net"], "icici": ["icicibank.com"],
    "sbi": ["sbi.co.in"], "paytm": ["paytm.com"], "swiggy": ["swiggy.in"],
    "zomato": ["zomato.com"], "reliance": ["ril.com", "jio.com"],
}

HUB_COUNTRIES = r"cambodia|myanmar|burma|laos|lao\s*pdr|thailand|vietnam|phnom\s*penh|bangkok|myawaddy|golden\s*triangle|sihanoukville"
HUB_ROLES = (r"data\s*entry|customer\s*(support|service|care)|tele\s*caller|telecaller|call\s*cent(?:er|re)|"
             r"it\s*(job|support|professional)|digital\s*marketing|crypto|sales\s*executive|chat\s*support|"
             r"tech(?:nical)?\s*support|software|operator|typist|online\s*(job|work)")

LOW_SKILL_CONTEXT = (r"data\s*entry|typing|copy\s*paste|form\s*filling|part[\s-]*time|work\s*from\s*home|wfh|"
                     r"fresher|no\s*experience|simple\s*(task|work)|online\s*(job|work)|captcha|survey|home[\s-]*based")


def _f(fid, sev, weight, en, evidence=""):
    return {"id": fid, "severity": sev, "weight": weight, "en": en, "evidence": evidence[:90]}


# (id, severity, weight, regex, english message)
TEXT_RULES = [
    ("fee_request", "high", 55,
     r"(registration|training|security|refundable|joining|processing|verification|kit|laptop|uniform|id\s*card|"
     r"onboarding|document|courier|visa|flight|ticket)\s*(fee|fees|charge|charges|deposit|amount|cost)"
     r"|(pay|deposit|transfer|send|remit)\s+(?:an?\s+)?(?:amount\s+of\s+)?(?:rs\.?|₹|inr)\s*[\d,]+"
     r"|refundable\s+(deposit|amount|fee)",
     "Asks you to pay money (fee / deposit / kit). Genuine employers do not charge candidates."),
    ("payment_channel", "high", 15,
     r"\bupi\b|paytm|phonepe|gpay|google\s*pay|qr\s*code|scan\s+(the\s+)?qr|account\s*(no|number)|\bifsc\b|\bneft\b|\bimps\b",
     "Gives UPI / QR / bank account details for payment."),
    ("otp_pin", "high", 60,
     r"upi\s*pin|atm\s*pin|\botp\b|\bcvv\b|card\s*number|net\s*banking\s*password",
     "Asks for OTP / PIN / card or banking secrets. No recruiter ever needs these."),
    ("urgency", "medium", 15,
     r"within\s+\d+\s*(hours?|hrs?|minutes?)|immediately|today\s+only|last\s+chance|limited\s+(seats|slots|vacanc)|"
     r"\burgent(ly)?\b|hurry|confirm\s+(by\s+)?today|offer\s+(will\s+)?expires?|expires?\s+(today|soon|in)",
     "Pressure to decide or pay immediately."),
    ("no_interview", "medium", 20,
     r"(no|without)\s+(any\s+)?interview|direct\s+(joining|selection|offer)|selected\s+without|no\s+interview\s+required",
     "Offer without a proper interview."),
    ("messaging_only", "medium", 12,
     r"(contact|message|chat|reach|join|text|connect)[^.\n]{0,40}(whatsapp|telegram)|telegram\s*(group|channel)|"
     r"join\s+(our\s+)?(whatsapp|telegram)|(whatsapp|telegram)\s+(only|number)|"
     r"only\s+(on|via|through|over)\s+(whatsapp|telegram)",
     "Hiring is happening only over WhatsApp / Telegram."),
    ("task_scam", "high", 35,
     r"like\s+(and\s+)?(subscribe|videos?)|rate\s+(products?|hotels?|apps?)|review\s+(products?|hotels?)|"
     r"task[\s-]*(based|completion)|complete\s+(simple\s+)?tasks?|prepaid\s+task|commission\s+(per|on)\s+task|"
     r"captcha\s+typing|youtube\s+(like|task)|instagram\s+(like|follow)",
     "Task / like / review style 'job' - a very common scam format."),
    ("visit_visa", "high", 35,
     r"(tourist|visit|visitor)\s*visa|visa\s+on\s+arrival|convert\s+(it\s+)?(in)?to\s+work(ing)?\s+visa",
     "Mentions a tourist / visit visa for a job - a known trafficking pattern."),
    ("free_travel", "medium", 15,
     r"free\s+(flight|ticket|visa|accommodation|food|stay)|(flight\s+)?tickets?\s+(will\s+be\s+)?provided|"
     r"we\s+(will|shall)\s+(book|arrange)\s+(your\s+)?(flight|ticket)",
     "Promises free ticket / visa / accommodation."),
    ("secrecy", "high", 25,
     r"(do\s*not|don'?t|never)\s+(tell|share|inform|discuss)[^.\n]{0,40}(family|parents|anyone|college|friends)|"
     r"keep\s+(this\s+)?(confidential|secret)",
     "Asks you to keep the offer secret from family / college."),
    ("docs_early", "medium", 15,
     r"(send|share|submit|upload|provide)\s+(your\s+)?(aadhaar|aadhar|pan|passport|bank|selfie)",
     "Asks for ID / bank documents before a proper hiring process."),
    ("guaranteed", "medium", 15,
     r"100\s*%\s*(guaranteed|placement|job)|guaranteed\s+(job|placement|selection)|assured\s+(job|placement)",
     "Claims a 100% guaranteed job."),
]


def levenshtein(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def registered_domain(host):
    host = re.sub(r"^www\.", "", (host or "").lower().strip().strip("."))
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in MULTI_TLDS:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def website_domain(url):
    if not url:
        return ""
    if "//" not in url:
        url = "http://" + url
    return registered_domain(urlparse(url).hostname or "")


def extract_entities(text):
    up = text.upper()
    return {
        "emails": sorted(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text))),
        "phones": sorted(set(re.findall(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)", text))),
        "urls": sorted(set(re.findall(r"https?://[^\s)>\"']+|(?:www\.)[^\s)>\"']+", text))),
        "cin": (re.findall(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b", up) or [""])[0],
        "gstin": (re.findall(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", up) or [""])[0],
    }


def _amount_to_monthly(text):
    """Largest monthly-equivalent pay figure mentioned, or 0."""
    best = 0.0
    pat = re.compile(r"(?:rs\.?|inr|₹)\s*([\d][\d,]*(?:\.\d+)?)\s*(k|lakhs?|lacs?|lpa)?", re.I)
    for m in pat.finditer(text):
        try:
            val = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        if unit == "k":
            val *= 1_000
        elif unit.startswith(("lakh", "lac", "lpa")):
            val *= 100_000
        window = text[m.end(): m.end() + 40].lower()
        if unit == "lpa" or re.search(r"per\s*annum|annum|annual|p\.?a\b", window):
            monthly = val / 12
        elif re.search(r"per\s*day|daily|/\s*day|a\s*day", window):
            monthly = val * 26
        elif re.search(r"per\s*week|weekly|/\s*week", window):
            monthly = val * 4.3
        elif re.search(r"per\s*month|monthly|/\s*month|\bpm\b|a\s*month", window):
            monthly = val
        else:
            continue
        best = max(best, monthly)
    return best


def text_flags(text):
    t = " ".join(text.split())
    low = t.lower()
    flags = []
    for fid, sev, weight, pattern, msg in TEXT_RULES:
        m = re.search(pattern, low, re.I)
        if m:
            flags.append(_f(fid, sev, weight, msg, m.group(0)))

    # Overseas pattern: scam-compound countries + typical lure roles
    hub = re.search(HUB_COUNTRIES, low)
    if hub:
        role = re.search(HUB_ROLES, low)
        if role:
            flags.append(_f("overseas_hub_role", "high", 60,
                            "Job in a known scam-compound region (Cambodia / Myanmar / Laos / Thailand...) for "
                            "data-entry / support / IT work. Thousands of Indians were trapped this way.",
                            f"{hub.group(0)} + {role.group(0)}"))
        else:
            flags.append(_f("overseas_hub", "high", 30,
                            "Job in a region where fake job offers have led to trafficking. Verify with MEA/eMigrate.",
                            hub.group(0)))
    elif re.search(r"abroad|overseas|foreign\s+(job|company)|international\s+(job|placement)|gulf|dubai|"
                   r"singapore|malaysia|saudi|qatar|kuwait|oman|bahrain", low):
        flags.append(_f("overseas_generic", "low", 10,
                        "Overseas job - the recruiting agent must be registered with the government (eMigrate).",
                        ""))

    # Unrealistic pay for fresher / low-skill work
    monthly = _amount_to_monthly(t)
    if monthly >= 60000 and re.search(LOW_SKILL_CONTEXT, low):
        flags.append(_f("high_pay", "medium", 20,
                        "Very high pay for a fresher / easy work.", f"~₹{int(monthly):,}/month"))
    elif monthly >= 150000 and re.search(r"intern|trainee|fresher", low):
        flags.append(_f("high_pay", "medium", 20,
                        "Very high pay for an intern / trainee.", f"~₹{int(monthly):,}/month"))
    return flags


def email_flags(sender, company, website, text):
    """Checks on recruiter email domain vs company / website."""
    flags, checks = [], []
    if not sender or "@" not in sender:
        return flags, checks
    dom = registered_domain(sender.split("@", 1)[1])
    claimed = f"{company} {text}".lower()

    if dom in FREE_EMAIL_DOMAINS:
        flags.append(_f("free_email", "medium", 20,
                        f"Recruiter uses a free email ({dom}). Companies hire from their own domain.", dom))
        checks.append({"id": "email", "label": "Recruiter email", "status": "bad",
                       "detail": f"Free email provider: {dom}"})
        return flags, checks

    matched_brand = False
    for brand, officials in BRAND_DOMAINS.items():
        if re.search(rf"\b{re.escape(brand)}\b", claimed):
            matched_brand = True
            if dom in officials:
                checks.append({"id": "email", "label": "Recruiter email", "status": "ok",
                               "detail": f"{dom} is an official {brand.upper()} domain."})
                break
            base = dom.split(".")[0]
            ob = [o.split(".")[0] for o in officials]
            if brand.replace(" ", "") in base or any(levenshtein(base, x) <= 2 for x in ob):
                flags.append(_f("lookalike_domain", "high", 50,
                                f"{dom} imitates the real {brand.upper()} domain ({', '.join(officials)}).", dom))
                checks.append({"id": "email", "label": "Recruiter email", "status": "bad",
                               "detail": f"Look-alike of {', '.join(officials)}"})
            else:
                flags.append(_f("lookalike_domain", "high", 40,
                                f"Message claims to be from {brand.upper()} but the email is from {dom}.", dom))
                checks.append({"id": "email", "label": "Recruiter email", "status": "bad",
                               "detail": f"Claims {brand.upper()} but domain is {dom}"})
            break

    wd = website_domain(website)
    if wd and not any(c["id"] == "email" for c in checks):
        if dom == wd:
            checks.append({"id": "email", "label": "Recruiter email", "status": "ok",
                           "detail": f"{dom} matches the company website."})
        else:
            flags.append(_f("website_mismatch", "medium", 25,
                            f"Email domain {dom} does not match the company website {wd}.", dom))
            checks.append({"id": "email", "label": "Recruiter email", "status": "warn",
                           "detail": f"{dom} vs website {wd}"})
    elif not any(c["id"] == "email" for c in checks):
        checks.append({"id": "email", "label": "Recruiter email", "status": "unknown",
                       "detail": f"{dom} - add the company website to compare."})
    return flags, checks


def level_for(score, flags):
    if any(f["id"] in {"otp_pin", "overseas_hub_role", "lookalike_domain"} for f in flags):
        return "high"
    if score >= 55:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def total_score(flags):
    return min(100, sum(f["weight"] for f in flags))
