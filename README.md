# Collections Voice Bot — Gnani.ai FDE Assignment

A production-ready voice collections bot for NBFCs targeting borrowers 1–30 DPD (Days Past Due). Built on **FastAPI + MongoDB + Redis**, integrated with the **Inya voice platform** by Gnani.ai.

# Demo Video Links

```
Youtube Link :- https://www.youtube.com/watch?v=UlADuBQMljo
Drive Link :- https://drive.google.com/file/d/1Ooqz0vWxU-SM4BdtzCTgFCKmB0DKyTCU/view?usp=sharing
```

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Tech Stack](#2-tech-stack)
3. [Project Structure](#3-project-structure)
4. [Data Models](#4-data-models)
5. [Backend Setup](#5-backend-setup)
6. [API Endpoints](#6-api-endpoints)
7. [Conversation Flow](#7-conversation-flow)
8. [Inya Platform Setup](#8-inya-platform-setup)
9. [Redis State Management](#9-redis-state-management)
10. [Sentiment Analysis](#10-sentiment-analysis)
11. [Environment Variables](#11-environment-variables)
12. [Running Locally](#12-running-locally)
13. [Testing with Postman](#13-testing-with-postman)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        INYA PLATFORM                            │
│                                                                 │
│  ┌──────────────┐   ┌─────────────────┐   ┌────────────────┐    │
│  │  Pre-call    │   │  Conversation   │   │  Post-Call     │    │
│  │  Variables   │   │  Flow           │   │  Action        │    │
│  │              │   │                 │   │                │    │
│  │ borrower_id  │   │ Dynamic Msg 1   │   │ log_outcome    │    │
│  │              │   │ (greeting)      │   │ → /call/end    │    │
│  └──────────────┘   │                 │   └────────────────┘    │
│                     │ Dynamic Msg 2   │                         │
│                     │ (language sel.) │                         │
│                     │                 │                         │
│                     │ LLM + Actions   │                         │
│                     │ process_message │                         │
│                     └────────┬────────┘                         │
└──────────────────────────────│──────────────────────────────────┘
                               │ Webhooks (via ngrok in dev)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FASTAPI BACKEND                             │
│                                                                 │
│  GET  /call/greeting    ← Dynamic Message 1 (greeting)          │
│  POST /call/language    ← Dynamic Message 2 (lang select)       │
│  POST /call/message     ← On-Call action (every turn)           │
│  POST /call/end         ← Post-Call action (call end)           │
│                                                                 │
│  ┌──────────────────┐   ┌──────────────┐   ┌───────────────┐    │
│  │ conversation_    │   │ intent_      │   │ outcome_      │    │
│  │ service.py       │   │ service.py   │   │ service.py    │    │
│  │                  │   │              │   │               │    │
│  │ State machine    │   │ Regex intent │   │ Log to MongoDB│    │
│  │ Lang selection   │   │ detection    │   │ Sentiment     │    │
│  │ Date extraction  │   │ EN + HI      │   │ analysis      │    │
│  └────────┬─────────┘   └──────────────┘   └───────────────┘    │
│           │                                                     │
└───────────│─────────────────────────────────────────────────────┘
            │
    ┌───────┴────────────────────┐
    │                            │
    ▼                            ▼
┌─────────┐              ┌─────────────┐
│  Redis  │              │  MongoDB    │
│         │              │             │
│ conv:   │              │ borrowers   │
│ {callid}│              │ call_logs   │
│         │              │ commitments │
│ retry:  │              │             │
│ {borrid}│              └─────────────┘
└─────────┘
```

### Call Flow Summary

```
1. Inya dials borrower
2. GET /call/greeting  → returns bilingual greeting text
3. Borrower responds ("Hindi" / "Yes" / "English")
4. POST /call/language → detects language, saves to MongoDB, returns EMI message
5. Borrower responds to EMI message
6. POST /call/message  → detects intent, returns next response
7. Steps 5–6 repeat until call resolves
8. POST /call/end      → logs outcome + sentiment to MongoDB
```

---

## 2. Tech Stack

| Layer             | Technology                       |
| ----------------- | -------------------------------- |
| Backend Framework | FastAPI (async)                  |
| Database          | MongoDB (via Motor async driver) |
| Cache / State     | Redis (via redis.asyncio)        |
| Voice Platform    | Inya by Gnani.ai                 |
| Tunnel (dev)      | ngrok                            |
| Language          | Python 3.11+                     |
| Runtime           | Uvicorn ASGI                     |

---

## 3. Project Structure

```
src/
├── app.py                          # FastAPI app, CORS, router registration
│
├── Config/
│   ├── db.py                       # MongoDB connection + collections
│   └── redis.py                    # Redis async client
│
├── Models/
│   ├── borrower.py                 # Borrower Pydantic model
│   ├── call_log.py                 # CallLog Pydantic model
│   ├── commitment.py               # Commitment Pydantic model
│   └── inya.py                     # Inya webhook payload models
│
├── Routes/
│   ├── borrower_router.py          # Borrower CRUD endpoints
│   ├── call_router.py              # Call webhook endpoints
│   └── public_router.py           # Health check
│
├── services/
│   ├── conversation_service.py     # Core state machine + bilingual responses
│   ├── intent_service.py           # Regex-based intent detection (EN + HI)
│   ├── outcome_service.py          # MongoDB logging + sentiment analysis
│   ├── escalation_service.py       # Escalation intent check
│   └── campaign_service.py         # Due borrowers for outbound campaign
│
└── utils/
    └── retry_manager.py            # Redis-based call retry logic
```

---

## 4. Data Models

### Borrower

```python
{
  "_id": ObjectId,           # MongoDB auto-generated, used as borrower_id
  "name": str,               # Full name
  "phone": str,              # Mobile number
  "dob": str,                # DOB (another way for verification)
  "emi_amount": float,       # EMI amount in INR
  "due_date": str,           # Due date e.g. "2025-06-01"
  "days_past_due": int,      # 1–30 DPD
  "language": str            # "en" or "hi" — updated during call
  "loan_account_number": str # Used for verification
}
```

### Call Log

```python
{
  "_id": ObjectId,
  "borrower_id": str,
  "call_id": str,            # Inya's call session ID
  "intent": str,             # Last detected intent
  "intent_history": list,    # All intents across turns
  "outcome": str,            # COMMITTED / ESCALATED / NO_ANSWER / WRONG_NUMBER / etc.
  "commitment_date": str,    # If borrower committed to pay
  "commitment_amount": float,
  "escalated": bool,
  "sentiment": {
    "label": str,            # POSITIVE / NEGATIVE / NEUTRAL
    "score": float           # 0.0 – 1.0
  },
  "duration_seconds": int,
  "timestamp": datetime
}
```

### Commitment

```python
{
  "_id": ObjectId,
  "borrower_id": str,
  "call_id": str,
  "commitment_date": str,
  "commitment_amount": float,
  "created_at": datetime
}
```

---

## 5. Backend Setup

### Install Dependencies

```bash
pip install -r requirements.txt
pip install ngrok #ngrok should be present in local machine
```

### requirements.txt

```
fastapi==0.111.0
uvicorn==0.29.0
motor==3.4.0
redis==5.0.4
python-dotenv==1.0.1
pydantic==2.7.1
pymongo==4.7.2
```

### .env File

```env
MONGO_URL
REDIS_HOST
REDIS_PORT
MAX_CALL_RETRIES=3
```

### Start MongoDB and Redis

```bash
# Redis-stack (with Docker)
- Start: Docker desktop
- Open terminal:
              - docker run -d --name redis-stack -p 6379:6379 -p 8001:8001 redis/redis-stack:latest
              - docker exec it <container_id>
```

### Run Backend

```bash
#First Terminal
./venv/Scripts/activate.ps1
fastapi dev src/app.py

```

### Expose to Internet via ngrok

```bash
#Second terminal
ngrok http 8000
# Copy the HTTPS URL e.g. https://abc123.ngrok-free.app
# Monitor traffic at http://localhost:4040
```

---

## 6. API Endpoints

### Borrower Endpoints

| Method | URL                                | Description                |
| ------ | ---------------------------------- | -------------------------- |
| POST   | `/borrower`                        | Add new borrower           |
| GET    | `/borrower/{id}`                   | Get borrower by ID         |
| GET    | `/borrower/search?borrower_id=xxx` | Search borrower            |
| GET    | `/borrowers`                       | List all borrowers         |
| PATCH  | `/borrower/{id}/language`          | Update language preference |

### Call Endpoints

| Method | URL                            | Caller                 | Description                             |
| ------ | ------------------------------ | ---------------------- | --------------------------------------- |
| GET    | `/call/greeting`               | Inya Dynamic Message 1 | Returns bilingual greeting              |
| POST   | `/call/language`               | Inya Dynamic Message 2 | Handles language selection              |
| POST   | `/call/message`                | Inya On-Call Action    | Processes every borrower utterance      |
| POST   | `/call/end`                    | Inya Post-Call Action  | Logs outcome + sentiment                |
| GET    | `/call/history/{borrower_id}`  | CRM / Internal         | Full call history + sentiment summary   |
| GET    | `/call/campaign/due-borrowers` | Campaign Tool          | List of borrowers due for outbound call |

## 7. Conversation Flow

### State Machine (stored in Redis per call)

```
awaiting = "identity_confirmation"
    │
    ├── text contains "hindi"  → language="hi", save to MongoDB
    │                            awaiting = "payment_intent"
    │                            → speak EMI message in Hindi
    │
    ├── text contains "english" / intent=YES → language="en", save to MongoDB
    │                            awaiting = "payment_intent"
    │                            → speak EMI message in English
    │
    └── intent=NO / WRONG_NUMBER → log WRONG_NUMBER, end_call

awaiting = "payment_intent"  (normal conversation turns)
    │
    ├── PAY_NOW       → log COMMITTED (today), end_call
    ├── PAY_LATER     → awaiting = "commitment_date", ask for date
    ├── CONFIRM_DATE  → log COMMITTED, end_call
    ├── CALLBACK      → log CALLBACK_REQUESTED, continue
    ├── WRONG_NUMBER  → log WRONG_NUMBER, end_call
    ├── DISPUTE       → log ESCALATED, escalate
    ├── FINANCIAL_DIFFICULTY → log ESCALATED, escalate
    ├── ABUSIVE       → log ESCALATED, escalate
    └── UNKNOWN       → fallback reprompt

awaiting = "commitment_date"
    └── any text → extract date, log COMMITTED, end_call
```

### Intent Detection (`intent_service.py`)

Intents are detected via regex patterns supporting both English and Hindi:

| Intent               | Example Triggers                 |
| -------------------- | -------------------------------- |
| YES                  | yes, haan, ji, correct, speaking |
| NO                   | no, nahi, wrong                  |
| LANG_ENGLISH         | english                          |
| LANG_HINDI           | hindi                            |
| PAY_NOW              | pay now, aaj de dunga            |
| PAY_LATER            | tomorrow, kal, will pay, pay by  |
| CONFIRM_DATE         | 15th June, 15/06, next Monday    |
| FINANCIAL_DIFFICULTY | no money, paisa nahi, can't pay  |
| CALLBACK_REQUESTED   | call back, busy, bad time        |
| WRONG_NUMBER         | wrong number, galat number       |
| ABUSIVE              | stop calling, harassment, court  |
| DISPUTE              | already paid, not my loan        |

### Bilingual Responses

All bot responses are templated in both English and Hindi in `conversation_service.py`:

```python
RESPONSES = {
    "en": { "emi_inform": "...", "ask_date": "...", "committed": "...", ... },
    "hi": { "emi_inform": "...", "ask_date": "...", "committed": "...", ... }
}
```

Language is selected during the call and persisted to MongoDB.

---

## 8. Inya Platform Setup

### Pre-call Variables

| Variable      | Type   | Sample Value               | Notes                          |
| ------------- | ------ | -------------------------- | ------------------------------ |
| `borrower_id` | String | `69ac367678cb369aadfd7e75` | MongoDB `_id` of test borrower |

> ⚠️ In Inya test mode, it uses the **saved sample value** — not what you type in the test popup. Update the sample value to change the test borrower.

---

### Dynamic Message 1 — Greeting

| Field          | Value                                                                               |
| -------------- | ----------------------------------------------------------------------------------- |
| Method         | GET                                                                                 |
| URL            | `https://<ngrok>/api/call/greeting?borrower_id={{borrower_id}}&call_id={{call_id}}` |
| Response field | `additional_info.inya_data.text`                                                    |

This fires at call start and returns the bilingual greeting. It also initializes Redis conversation state with `awaiting = "identity_confirmation"`.

---

### Dynamic Message 2 — Language Selection

| Field          | Value                                                                                    |
| -------------- | ---------------------------------------------------------------------------------------- |
| Method         | POST                                                                                     |
| URL            | `https://<ngrok>/api/call/language`                                                      |
| Body           | `{"borrower_id": "{{borrower_id}}", "call_id": "{{call_id}}", "text": "{{asr_output}}"}` |
| Response field | `additional_info.inya_data.text`                                                         |

This fires after the borrower responds to the greeting. It bypasses the LLM entirely — the borrower's response goes directly to your API which detects "Hindi" or "English/Yes" and returns the EMI message in the correct language. Also updates `language` field in MongoDB.

---

### Actions

#### `process_message` (On-Call)

| Field                     | Value                                                                                                      |
| ------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Integration               | Handle_Message (CUSTOM)                                                                                    |
| Type                      | On-Call                                                                                                    |
| Method                    | POST                                                                                                       |
| URL                       | `https://<ngrok>/api/call/message`                                                                         |
| Before API Call Variables | **None — delete all**                                                                                      |
| Body                      | `{"call_id": "{{call_id}}", "borrower_id": "{{borrower_id}}", "text": "{{asr_output}}", "language": "en"}` |

**After API Call Variables:**
| Variable | Prompt |
|---|---|
| `bot_response` | Extract the `response` field from the API JSON response |

**Description:**

```
Call this action after EVERY borrower utterance without exception.
Pass the borrower's exact words as "text". Speak only bot_response.
Do NOT echo the borrower. Do NOT respond yourself.
```

---

#### `log_outcome` (Post-Call)

| Field       | Value                                                                                                          |
| ----------- | -------------------------------------------------------------------------------------------------------------- |
| Integration | End_call (CUSTOM)                                                                                              |
| Type        | Post-Call                                                                                                      |
| Method      | POST                                                                                                           |
| URL         | `https://<ngrok>/api/call/end`                                                                                 |
| Body        | `{"call_id": "{{call_id}}", "borrower_id": "{{borrower_id}}", "event": "call_ended", "duration_seconds": "0"}` |

**Description:**

```
ALWAYS call this action at the end of every call without exception.
Call when borrower commits, wrong number, financial difficulty, or call ends for any reason.
```

---

### System Prompt

```
You are a Loan Collection Voice Agent. You have two actions: process_message and log_outcome.

STRICT RULES — NO EXCEPTIONS:
- NEVER generate any response yourself
- NEVER echo or repeat what the borrower said
- NEVER say anything not returned by process_message
- Speak only what bot_response contains
- NEVER announce actions you are calling
- NEVER say system errors or missing variables

YOUR ONLY WORKFLOW:
Step 1 — The greeting is handled automatically. Do nothing at call start.
Step 2 — Borrower says ANYTHING → immediately call process_message.
         Pass borrower_id and the borrower's exact spoken words as text.
Step 3 — Speak ONLY the value of bot_response returned by process_message.
Step 4 — Repeat Step 2 and Step 3 for every single turn without exception.
Step 5 — When call ends for any reason → call log_outcome silently.

YOU ARE A RELAY. YOU DO NOT THINK. YOU DO NOT RESPOND.
Borrower speaks → process_message → speak bot_response → wait.
First response, second response, every response — always process_message first.
No exceptions. Ever.
```

---

### LLM Settings

| Setting     | Value        |
| ----------- | ------------ |
| Provider    | Gnani        |
| Model       | Gnani SLM v2 |
| Temperature | 0.3          |
| Max Tokens  | 300          |

### Voice (TTS)

| Setting        | Value      |
| -------------- | ---------- |
| Service        | GnaniPro   |
| Rate of Speech | Normal / 1 |

### Transcriber (ASR)

| Setting             | Value             |
| ------------------- | ----------------- |
| Provider            | Gnani             |
| Model               | Gnani Transcriber |
| Allow Interruptions | ON                |

### Call Transfer

| Setting          | Value                                                   |
| ---------------- | ------------------------------------------------------- |
| Trigger          | Financial difficulty, dispute, abusive, requests human  |
| Transfer Message | "Please hold while I connect you to a support officer." |

---

## 9. Redis State Management

### Conversation State (`conv:{call_id}`)

```json
{
  "turn": 2,
  "intent_history": ["YES", "PAY_LATER"],
  "awaiting": "commitment_date",
  "language": "hi",
  "borrower_id": "69ac367678cb369aadfd7e75",
  "commitment_date": null
}
```

TTL: 1800 seconds (30 minutes). Cleared on call end.

### Retry Counter (`retry:{borrower_id}`)

```
retry:69ac367678cb369aadfd7e75 → 2
```

TTL: 86400 seconds (24 hours). Max retries configurable via `MAX_CALL_RETRIES` env var (default 3).

---

## 10. Sentiment Analysis

Sentiment is derived from `intent_history` and final `outcome` at call end:

| Outcome            | Sentiment                |
| ------------------ | ------------------------ |
| COMMITTED          | POSITIVE (score 0.7–1.0) |
| ESCALATED          | NEGATIVE (score 0.0–0.2) |
| NO_ANSWER          | NEUTRAL (score 0.5)      |
| WRONG_NUMBER       | NEUTRAL (score 0.5)      |
| CALLBACK_REQUESTED | NEUTRAL (score 0.55)     |

Call history endpoint returns per-call sentiment and overall summary:

```json
{
  "summary": {
    "total_calls": 3,
    "outcomes": { "committed": 1, "escalated": 0, "no_answer": 1, ... },
    "overall_sentiment": "POSITIVE",
    "sentiment_breakdown": { "positive": 1, "negative": 0, "neutral": 2 },
    "most_common_intent": "PAY_LATER",
    "last_call_at": "2025-06-01T10:30:00"
  }
}
```

---

## 11. Environment Variables

| Variable           | Default                     | Description                             |
| ------------------ | --------------------------- | --------------------------------------- |
| `MONGO_URL`        | `mongodb://localhost:27017` | MongoDB connection string               |
| `REDIS_HOST`       | `localhost`                 | Redis host                              |
| `REDIS_PORT`       | `6379`                      | Redis port                              |
| `MAX_CALL_RETRIES` | `3`                         | Max retry attempts per borrower per day |

---

## 12. Running Locally

```bash
# 1. Clone and install
pip install -r requirements.txt
pip install ngrok

# 2. Start services
# Redis-stack (with Docker)
- Start: Docker desktop
- Open terminal:
              - docker run -d --name redis-stack -p 6379:6379 -p 8001:8001 redis/redis-stack:latest
              - docker exec it <container_id>

# 3. Create .env

# 4. Start backend
./venv/Scripts/activate.ps1
fastapi dev src/app.py

# 5. Expose via ngrok
ngrok http 8000

# 6. Update ngrok URL in all Inya action URLs and Dynamic Message URLs
```

---

## 13. Testing with Postman

### Add a Test Borrower

```
POST http://localhost:8000/api/borrower
Content-Type: application/json

{
  "name": "Harshit Choubey",
  "phone": "+919876543210",
  "emi_amount": 5000,
  "due_date": "2025-05-01",
  "days_past_due": 15,
  "language": "en"
}
```

Copy the `_id` from response — use it as `borrower_id` in Inya Pre-call Variables sample value.

### Test Greeting

```
GET http://localhost:8000/api/call/greeting?borrower_id=<_id>&call_id=test_01
```

### Test Language Selection

```
POST http://localhost:8000/api/call/language
Content-Type: application/json

{ "borrower_id": "<_id>", "call_id": "test_01", "text": "Hindi" }
```

### Test Conversation Turn

```
POST http://localhost:8000/api/call/message
Content-Type: application/json

{ "borrower_id": "<_id>", "call_id": "test_01", "text": "I will pay by 15th June" }
```

### Test Call End

```
POST http://localhost:8000/api/call/end
Content-Type: application/json

{ "borrower_id": "<_id>", "call_id": "test_01", "event": "call_ended" }
```

### Check Call History

```
GET http://localhost:8000/api/call/history/<_id>
```

---

## Known Limitations

- Gnani SLM cannot reliably call actions silently — first turn language selection moved to Direct Dynamic Message to bypass LLM entirely
- `call_id` from Inya may come as `sender_id` — backend handles both
- Date extraction uses regex — works for common formats but may miss complex expressions
- Hindi support is Hinglish (transliterated) — not Devanagari script
