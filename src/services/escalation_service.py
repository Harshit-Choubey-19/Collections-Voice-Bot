ESCALATION_INTENTS = {
    "FINANCIAL_DIFFICULTY",
    "ABUSIVE",
    "DISPUTE",
}


def should_escalate(intent: str) -> bool:
    return intent in ESCALATION_INTENTS