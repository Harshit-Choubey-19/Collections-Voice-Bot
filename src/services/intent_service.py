import re
from typing import Tuple

INTENT_PATTERNS = {
    "YES": [
        r"\byes\b", r"\byeah\b", r"\bya\b", r"\byep\b",
        r"\bhaan\b", r"\bhaa\b", r"\bha\b", r"\bji\b",
        r"\bji haan\b", r"\bji ha\b",
        r"\bcorrect\b", r"\bright\b", r"\bspeaking\b",
        r"\bthats me\b", r"\bthat's me\b",
        r"\bok\b", r"\bokay\b",              # people often say "ok" to confirm
    ],
    "NO": [
        r"\bno\b", r"\bnope\b",
        r"\bnahi\b", r"\bnahin\b", r"\bnaa\b",
        r"\bnot me\b", r"\bwrong\b",
        r"\bwrong number\b",
    ],
    "LANG_HINDI": [
        r"\bhindi\b",
        r"\bhindi mein\b",
        r"\bhindi chahiye\b",
        r"\bhindi bolna\b",
        r"\bmujhe hindi\b",
    ],
    "LANG_ENGLISH": [
        r"\benglish\b",
        r"\benglish mein\b",
        r"\benglish chahiye\b",
        r"\bi want english\b",
    ],
    "PAY_NOW": [
        r"\bpay(ing)?\s*(now|today|right now|immediately)\b",
        r"\bpayment\s*(done|complete|ready)\b",
        r"\bi('ll| will) pay (now|today)\b",
        r"\baaj (de|pay|bhar)\b",
    ],
    "PAY_LATER": [
        r"\btomorrow\b", r"\bnext week\b", r"\bfew days\b",
        r"\bafter\s*(salary|weekend|month)\b",
        r"\bkal\b", r"\bparso\b",
        r"\bwill pay\b", r"\bpay by\b",
    ],
    "FINANCIAL_DIFFICULTY": [
        r"\bno money\b", r"\bfinancial (problem|crisis|trouble|difficulty)\b",
        r"\bcan('t| not) (pay|afford)\b",
        r"\blost (job|work)\b", r"\bunemployed\b",
        r"\bpaisa nahi\b",
        r"\bmedical (emergency|expense)\b",
    ],
    "CALLBACK_REQUESTED": [
        r"\bcall (back|later|again)\b",
        r"\bnot (a good|right) time\b",
        r"\bbusy\b", r"\bin a meeting\b",
        r"\bbad time\b",
    ],
    "WRONG_NUMBER": [
        r"\bwrong number\b", r"\bno such (person|borrower)\b",
        r"\bi('m| am) not\s+\w+\b",
        r"\bgalat number\b",
    ],
    "ABUSIVE": [
        r"\bstop calling\b", r"\bdo not call\b", r"\bdon't call\b",
        r"\bharassment\b", r"\bpolichunga\b", r"\bcourt\b",
    ],
    "DISPUTE": [
        r"\balready paid\b", r"\bpayment done\b",
        r"\breceived no (loan|amount)\b",
        r"\bnot my loan\b", r"\bdispute\b",
    ],
    "CONFIRM_DATE": [
        r"\b(will pay|pay|paying)\s+(on|by)\s+\d{1,2}",
        r"\b\d{1,2}(st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b\d{1,2}[/-]\d{1,2}\b",
        r"\bnext (monday|tuesday|wednesday|thursday|friday)\b",
    ],
}


def detect_intent(text: str) -> Tuple[str, float]:
    text_lower = text.lower().strip()
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return intent, 1.0
    return "UNKNOWN", 0.5