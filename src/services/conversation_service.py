from services.intent_service import detect_intent

async def handle_conversation(borrower, user_text):

    intent = detect_intent(user_text)

    if intent == "PAY_NOW":

        return {
            "intent": intent,
            "message": "Thank you. Please make the payment today."
        }

    if intent == "PAY_LATER":

        return {
            "intent": intent,
            "message": "Sure. When will you make the payment?"
        }

    if intent == "FINANCIAL_DIFFICULTY":

        return {
            "intent": intent,
            "message": "I understand your situation. I will connect you with a support agent."
        }

    if intent == "CALL_BACK":

        return {
            "intent": intent,
            "message": "Sure. When should we call you again?"
        }

    if intent == "WRONG_NUMBER":

        return {
            "intent": intent,
            "message": "Sorry for the inconvenience."
        }

    return {
        "intent": intent,
        "message": "Could you please clarify your payment plan?"
    }