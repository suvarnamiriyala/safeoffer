# SafeOffer - working prototype

AI-assisted job-offer verification and interview safety for students in India.

## Run it

```bash
pip install fastapi uvicorn requests pillow pytesseract pdfplumber pypdf   # + tesseract-ocr installed on the system
cd safeoffer
uvicorn app:app --port 8000
# open http://localhost:8000   (use localhost, so the browser allows location access)
```

Optional environment variables (the app works without them):

| Variable | Adds |
|---|---|
| `GEMINI_API_KEY` | Plain-language AI explanation, in the chosen language. `GEMINI_MODEL` overrides the model name (default `gemini-2.5-flash`). |
| `GOOGLE_MAPS_API_KEY` | Automatic Google Places lookup of the registered address ("no business found" flag). |

Run the tests: `python3 tests/test_core.py` (38 checks).

## What works (tested)

| Feature | Status |
|---|---|
| Offer analysis (pasted text, PDF, scanned PDF, photo via OCR) | Working. 12 text rules + overseas/trafficking pattern, pay check |
| Recruiter email check (free email, look-alike of TCS/Infosys/etc., mismatch with website) | Working |
| CIN and GSTIN checks (format, GSTIN check digit, company age, PAN type vs "Pvt Ltd") | Working, **format only** |
| Registered address vs interview location (area/PIN match, hotel/cafe/residential flags, Maps links) | Working |
| Post-call questionnaire (11 questions, no recording) | Working |
| Low / Medium / High risk with reasons and next steps | Working |
| English / Hindi / Telugu | Results headline, next steps, flag titles and questionnaire are translated. Other languages need `GEMINI_API_KEY` (not built yet) |
| Live location sharing, arrival check-in, SOS | Working with a **tracking link** the contact opens in a browser |

## What is NOT real yet

- **MCA / GST lookup:** there is no free official API, so the app validates the number's format and links to the official portal. It does not confirm the company is active.
- **Google Maps lookup:** code is written but untested (needs your API key). Without a key, the app shows Maps links only.
- **Gemini:** code is written but untested (needs your key).
- **eMigrate:** link only, no automatic agent lookup.
- **SOS / check-in delivery:** the contact sees the live tracking page; push / SMS is a stub in `safety.py` (`notify()`). Plug in Firebase Cloud Messaging or an SMS/WhatsApp gateway there. Sessions are in memory (restart clears them); swap for Firestore.
- **Stack differences:** built on Starlette (what FastAPI is built on) and pdfplumber instead of FastAPI / PyMuPDF because those were not installable here. Routes in `app.py` port to FastAPI directly. The front end is a plain web page, not Flutter.
- **OCR:** English + Hindi. Telugu text needs `tesseract-ocr-tel`.
- **Hindi/Telugu text** was written by an AI and should be reviewed by a native speaker before a public demo.

The score is a risk estimate, not a verdict. A low score means no tricks were found in what was entered.

## Files

- `app.py` routes · `analyzer.py` combines checks · `rules.py` scam rules · `verify.py` CIN/GSTIN/address
- `callcheck.py` questionnaire · `extract.py` PDF/OCR · `explain.py` Gemini · `safety.py` sharing/SOS · `i18n.py` translations
- `static/index.html` app · `static/track.html` contact's tracking page · `samples/` test offer files
