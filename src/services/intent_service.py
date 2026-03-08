import re
from typing import Tuple

# ─── Intent keyword maps (expand as needed per language) ──────────────────────

INTENT_PATTERNS = {
    "PAY_NOW": [
        r"\bpay(ing)?\s*(now|today|right now|immediately)\b",
        r"\bpayment\s*(done|complete|ready)\b",
        r"\bi('ll| will) pay (now|today)\b",
        r"\aaj (de|pay|bhar)\b",           # Hindi: today give/pay
    ],
    "PAY_LATER": [
        r"\btomorrow\b", r"\bnext week\b", r"\bfew days\b",
        r"\bafter\s*(salary|weekend|month)\b",
        r"\bkal\b", r"\bparso\b",           # Hindi: tomorrow, day after
        r"\bwill pay\b", r"\bpay by\b",
    ],
    "FINANCIAL_DIFFICULTY": [
        r"\bno money\b", r"\bfinancial (problem|crisis|trouble|difficulty)\b",
        r"\bcan('t| not) (pay|afford)\b",
        r"\blost (job|work)\b", r"\bunemployed\b",
        r"\bpaisa nahi\b",                  # Hindi: no money
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
        r"\bgalat number\b",               # Hindi: wrong number
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
       r"\b(will pay|pay|paying)\s+(on|by)\s+\d{1,2}",          # "pay by 15"
       r"\b\d{1,2}(st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",  # "15th June"
       r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
       r"\b\d{1,2}[/-]\d{1,2}\b",                                # "15/06"
       r"\bnext (monday|tuesday|wednesday|thursday|friday)\b",
    ],
}


def detect_intent(text: str) -> Tuple[str, float]:
    """
    Returns (intent, confidence_score).
    confidence_score is simple: 1.0 for direct match, 0.5 for fallback.
    """
    text_lower = text.lower().strip()

    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return intent, 1.0

    return "UNKNOWN", 0.5