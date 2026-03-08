# Inya Platform Role:

The Inya platform is assumed to handle

- outbound call orchestration
- speech-to-text conversion
- text-to-speech synthesis

Our backend acts as the conversational intelligence layer
that processes borrower responses and returns the next agent response.

# Example Integration Flow with Inya

Borrower picks call
│
│
INYA converts voice → text
│
│
POST: /call/respond
│
FastAPI processes intent
│
MongoDB logs outcome
│
Response returned
│
INYA converts text → speech
│
Borrower hears response

# Architecture diagram

+----------------------+
| Borrower Phone |
+----------+-----------+
|
v
+----------------------+
| Inya Voice Agent |
| STT / TTS |
+----------+-----------+
|
v
+----------------------+
| FastAPI Backend |
| Intent Detection |
| Conversation Logic |
+----------+-----------+
|
v
+----------------------+
| MongoDB | Redis |
+----------------------+
