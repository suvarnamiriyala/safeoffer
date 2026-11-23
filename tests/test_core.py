"""Run:  python3 tests/test_core.py   (from the safeoffer folder)"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_MAPS_API_KEY", None)

import analyzer, verify, safety, callcheck  # noqa: E402

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {extra}")


def ids(r):
    return {f["id"] for f in r["flags"]}


print("Fake: registration fee + urgency + free email")
r = analyzer.analyze_offer({"text": "Congratulations! You are selected as TCS intern. Pay Rs 2000 registration fee via UPI "
                                    "within 2 hours or the offer expires. Contact on WhatsApp.",
                            "recruiter_email": "tcs.hr.jobs@gmail.com"})
check("level is high", r["risk"]["level"] == "high", r["risk"])
check("fee flagged", "fee_request" in ids(r))
check("urgency flagged", "urgency" in ids(r))
check("free email flagged", "free_email" in ids(r))

print("Fake: Cambodia data entry")
r = analyzer.analyze_offer({"text": "Urgent hiring data entry operators in Cambodia. Salary Rs 80,000 per month. "
                                    "Free flight ticket and accommodation. Come on tourist visa, we convert to work visa."})
check("hub+role flagged", "overseas_hub_role" in ids(r))
check("visit visa flagged", "visit_visa" in ids(r))
check("high", r["risk"]["level"] == "high")
check("eMigrate link given", any("emigrate" in l["url"] for l in r["links"]))
check("overseas step added", len(r["next_steps"]) == 5)

print("Look-alike domain")
r = analyzer.analyze_offer({"text": "Offer letter from TCS. Join us.", "company": "TCS",
                            "recruiter_email": "hr@tcs-careers.in"})
check("lookalike flagged", "lookalike_domain" in ids(r))
check("high", r["risk"]["level"] == "high")

print("Genuine-looking offer")
genuine = ("Dear Anil, we are pleased to offer you the position of Software Engineer Trainee at Infosys. "
           "Your interview on 12 Nov was conducted over video. Joining date 5 Jan. Annual CTC Rs 3.6 LPA. "
           "Please report to Infosys Campus, Electronics City, Bengaluru 560100 with your original certificates.")
r = analyzer.analyze_offer({"text": genuine, "company": "Infosys Limited", "recruiter_email": "careers@infosys.com",
                            "applied": "yes", "had_interview": "yes"})
check("low risk", r["risk"]["level"] == "low", r["risk"])
check("email ok", any(c["id"] == "email" and c["status"] == "ok" for c in r["checks"]))

print("Task scam")
r = analyzer.analyze_offer({"text": "Work from home! Like YouTube videos and complete simple tasks. Earn Rs 5000 per day. Join our Telegram group."})
check("task scam flagged", "task_scam" in ids(r))
check("high pay flagged", "high_pay" in ids(r))

print("CIN / GSTIN")
c = verify.parse_cin("U72900KA2015PTC080000")
check("CIN parses", c and c["valid"] and c["state"] == "KA" and c["year"] == 2015, c)
check("bad CIN rejected", not verify.parse_cin("U1234")["valid"])
check("future-year CIN rejected", not verify.parse_cin("U72900KA2099PTC080000")["valid"])
g = "27AAPFU0939F1ZV"
check("GSTIN checksum matches known sample", verify.validate_gstin(g)["valid"], verify.validate_gstin(g))
bad = g[:-1] + ("A" if g[-1] != "A" else "B")
check("tampered GSTIN rejected", not verify.validate_gstin(bad)["valid"])
base = "27ABCPD1234E1Z"  # PAN 4th letter P = individual
indiv = base + verify.gstin_checksum(base + "0")
r = analyzer.analyze_offer({"text": "Offer", "company": "Acme Pvt Ltd", "gstin": indiv})
check("individual GSTIN vs Pvt Ltd flagged", "gstin_entity_mismatch" in ids(r), (indiv, r["flags"]))
r = analyzer.analyze_offer({"text": "Offer", "company": "Acme Pvt Ltd", "gstin": g})
check("firm GSTIN vs Pvt Ltd not flagged here", "gstin_entity_mismatch" not in ids(r))
new_year = time.gmtime().tm_year
r = analyzer.analyze_offer({"text": "Offer", "company": "Brightpath Pvt Ltd", "cin": f"U72900TG{new_year}PTC123456"})
check("brand-new company flagged", "company_new" in ids(r))

print("Address checks")
r = analyzer.analyze_offer({"text": "Interview details inside", "company": "Acme Pvt Ltd",
                            "registered_address": "4th Floor, Plot 12, Hitech City Road, Madhapur, Hyderabad 500081",
                            "interview_address": "Hotel Sunrise, Room 204, Dwaraka Nagar, Visakhapatnam 530016"})
check("public place flagged", "address_public_place" in ids(r))
check("mismatch flagged", "address_mismatch" in ids(r))
r = analyzer.analyze_offer({"text": "Interview details", "company": "Acme Pvt Ltd",
                            "registered_address": "4th Floor, Plot 12, Hitech City Road, Madhapur, Hyderabad 500081",
                            "interview_address": "Plot 12, Hitech City Road, Madhapur, Hyderabad 500081"})
check("same address ok", "address_mismatch" not in ids(r), ids(r))

print("Post-call questionnaire")
r = analyzer.analyze_call({"q_money": True, "q_urgency": True, "q_otp": False})
check("fee+urgency high", r["risk"]["level"] == "high", r["risk"])
r = analyzer.analyze_call({"q_money": False, "q_urgency": False, "q_otp": False})
check("all no -> low", r["risk"]["level"] == "low", r["risk"])
r = analyzer.analyze_call({"q_urgency": True, "q_messaging": True})
check("two medium signs -> medium", r["risk"]["level"] == "medium", r["risk"])
r = analyzer.analyze_call({"q_money": True}, lang="te")
check("telugu question title", any("డబ్బు" in f["title"] for f in r["flags"]))
r = analyzer.analyze_offer({"text": "Pay Rs 1000 registration fee"}, "hi")
check("hindi headline", "उच्च" in r["headline"])

print("Safety session")
sid = safety.start({"name": "Riya", "company": "Acme", "arrive_in_min": 30, "contact_name": "Mom"})
safety.update_location(sid, 17.0005, 81.804)
v = safety.view(sid)
check("travelling with location", v["status"] == "travelling" and v["location"]["lat"] == 17.0005)
check("arrived", safety.arrived(sid)["status"] == "arrived")
check("sos", safety.sos(sid)["status"] == "sos")
sid2 = safety.start({"name": "Ravi", "arrive_in_min": 1})
safety.SESSIONS[sid2]["due"] = time.time() - 5
check("overdue when check-in missed", safety.view(sid2)["status"] == "overdue")
check("overdue event logged", any(e["type"] == "overdue" for e in safety.view(sid2)["events"]))
check("safe stops sharing", safety.safe(sid2)["status"] == "done")
try:
    safety.update_location(sid, 999, 0)
    check("bad coords rejected", False)
except ValueError:
    check("bad coords rejected", True)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
