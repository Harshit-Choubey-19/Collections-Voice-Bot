def should_escalate(intent):

    escalation_cases = [
        "FINANCIAL_DIFFICULTY",
        "ABUSIVE"
    ]

    return intent in escalation_cases