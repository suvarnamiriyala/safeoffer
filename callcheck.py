"""Post-call questionnaire. The call is never recorded; the student answers questions afterwards."""
from rules import _f

# id, weight, severity, {lang: question}
QUESTIONS = [
    ("q_money", 55, "high", {
        "en": "Did they ask you to pay any money (registration, training, kit, deposit, visa, ticket)?",
        "hi": "क्या उन्होंने कोई पैसा मांगा (रजिस्ट्रेशन, ट्रेनिंग, किट, डिपॉजिट, वीज़ा, टिकट)?",
        "te": "వారు డబ్బు అడిగారా (రిజిస్ట్రేషన్, ట్రైనింగ్, కిట్, డిపాజిట్, వీసా, టికెట్)?"}),
    ("q_otp", 60, "high", {
        "en": "Did they ask for an OTP, UPI/ATM PIN, card details or bank login?",
        "hi": "क्या उन्होंने OTP, UPI/ATM PIN, कार्ड या बैंक लॉगिन की जानकारी मांगी?",
        "te": "వారు OTP, UPI/ATM PIN, కార్డ్ వివరాలు లేదా బ్యాంక్ లాగిన్ అడిగారా?"}),
    ("q_abroad_visit", 45, "high", {
        "en": "Is the job abroad (esp. Cambodia, Myanmar, Laos, Thailand, Vietnam) or did they say go on a tourist/visit visa?",
        "hi": "क्या नौकरी विदेश में है (खासकर कंबोडिया, म्यांमार, लाओस, थाईलैंड, वियतनाम) या उन्होंने टूरिस्ट/विज़िट वीज़ा पर जाने को कहा?",
        "te": "ఉద్యోగం విదేశంలో ఉందా (ముఖ్యంగా కంబోడియా, మయన్మార్, లావోస్, థాయిలాండ్, వియత్నాం) లేదా టూరిస్ట్/విజిట్ వీసాపై వెళ్లమన్నారా?"}),
    ("q_secrecy", 30, "high", {
        "en": "Did they tell you to keep it secret from family, college or friends?",
        "hi": "क्या उन्होंने परिवार, कॉलेज या दोस्तों से इसे गुप्त रखने को कहा?",
        "te": "కుటుంబం, కాలేజీ లేదా స్నేహితులకు రహస్యంగా ఉంచమని చెప్పారా?"}),
    ("q_urgency", 20, "medium", {
        "en": "Did they push you to decide or pay today / within a few hours?",
        "hi": "क्या उन्होंने आज ही या कुछ घंटों में फैसला/भुगतान करने का दबाव डाला?",
        "te": "ఈరోజే లేదా కొన్ని గంటల్లో నిర్ణయం/చెల్లింపు చేయమని ఒత్తిడి చేశారా?"}),
    ("q_no_interview", 20, "medium", {
        "en": "Were you offered the job without a proper interview?",
        "hi": "क्या आपको बिना उचित इंटरव्यू के नौकरी का ऑफर दिया गया?",
        "te": "సరైన ఇంటర్వ్యూ లేకుండా ఉద్యోగ ఆఫర్ ఇచ్చారా?"}),
    ("q_no_company_info", 20, "medium", {
        "en": "Did they avoid giving the company address, official website or company email?",
        "hi": "क्या उन्होंने कंपनी का पता, आधिकारिक वेबसाइट या कंपनी ईमेल देने से बचा?",
        "te": "కంపెనీ చిరునామా, అధికారిక వెబ్‌సైట్ లేదా కంపెనీ ఈమెయిల్ ఇవ్వకుండా తప్పించుకున్నారా?"}),
    ("q_high_pay", 15, "medium", {
        "en": "Is the salary much higher than normal for a fresher or for this kind of work?",
        "hi": "क्या सैलरी फ्रेशर या इस काम के लिए सामान्य से बहुत ज्यादा है?",
        "te": "జీతం ఫ్రెషర్‌కు లేదా ఈ పనికి సాధారణం కంటే చాలా ఎక్కువగా ఉందా?"}),
    ("q_messaging", 12, "medium", {
        "en": "Did they contact you only on WhatsApp/Telegram or a personal number?",
        "hi": "क्या उन्होंने सिर्फ WhatsApp/Telegram या निजी नंबर से संपर्क किया?",
        "te": "వారు కేవలం WhatsApp/Telegram లేదా వ్యక్తిగత నంబర్ నుండి సంప్రదించారా?"}),
    ("q_threat", 15, "medium", {
        "en": "Did they get angry, threaten you or say the offer is cancelled when you hesitated?",
        "hi": "जब आपने हिचकिचाहट दिखाई तो क्या वे गुस्सा हुए, धमकाया या ऑफर रद्द करने को कहा?",
        "te": "మీరు సందేహిస్తే వారు కోపగించారా, బెదిరించారా లేదా ఆఫర్ రద్దు అన్నారా?"}),
    ("q_not_applied", 15, "medium", {
        "en": "Did they call you about a job you never applied for?",
        "hi": "क्या उन्होंने ऐसी नौकरी के लिए फोन किया जिसके लिए आपने आवेदन ही नहीं किया था?",
        "te": "మీరు దరఖాస్తు చేయని ఉద్యోగం గురించి ఫోన్ చేశారా?"}),
]

EN = {q[0]: q[3]["en"] for q in QUESTIONS}


def questions(lang="en"):
    return [{"id": q[0], "text": q[3].get(lang) or q[3]["en"]} for q in QUESTIONS]


def call_flags(answers):
    """answers: {question_id: bool}. Returns flags for every 'yes'."""
    flags = []
    for qid, weight, sev, texts in QUESTIONS:
        if answers.get(qid) is True:
            flags.append(_f(qid, sev, weight, texts["en"]))
    return flags
