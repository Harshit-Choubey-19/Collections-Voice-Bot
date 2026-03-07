def detect_intent(text: str):

    text = text.lower()

    if "pay now" in text or "today" in text:
        return "PAY_NOW"

    if "tomorrow" in text or "next week" in text:
        return "PAY_LATER"

    if "financial problem" in text or "no money" in text:
        return "FINANCIAL_DIFFICULTY"

    if "call later" in text:
        return "CALL_BACK"

    if "wrong number" in text:
        return "WRONG_NUMBER"

    if "stop calling" in text:
        return "ABUSIVE"

    return "UNKNOWN"