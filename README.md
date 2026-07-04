# ARIA — AI Realtime Intelligence Agent
### Voice/Realtime Customer Support Agent | Powered by Google Gemini API

> A full-stack, production-quality voice AI agent combining **Speech-to-Text**, **LLM function calling**, and **Text-to-Speech** in a single pipeline — plus a real-time speech-to-speech mode via the **Gemini Live API**.

---

## 🚀 Quick Start

### 1. Get your Gemini API Key
Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → Create API Key (free tier works)

### 2. Configure environment
```powershell
Copy-Item .env.example .env
notepad .env   # Paste your GEMINI_API_KEY
```

### 3. Run (one command)
```powershell
.\start.ps1
```

Then open **http://localhost:5173** in your browser.

---

## 📋 Manual Setup (if start.ps1 doesn't work)

**Terminal 1 — Backend:**
```powershell
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```powershell
cd frontend
npm install
npm run dev
```

---

## 🎯 How to Use

### Classic Pipeline Mode (default)
1. Click **Hold to speak** → talk → release
2. Watch: transcript appears → ARIA reasons → tool calls fire → audio plays back
3. Or click any **quick chip** to skip recording (text input)

### Live API Mode (Realtime)
1. Switch toggle to **🔴 Live API**
2. Click **Connect** — waits for Gemini Live API handshake
3. Hold **Hold to speak** → talk in real-time → Gemini streams audio back instantly
4. Built-in VAD: Gemini detects when you stop speaking automatically

---

## 🛠️ Architecture

```
Browser (React/Vite)
    │
    ├── Classic Mode: POST /api/chat  (audio blob)
    │     ├── Gemini 2.5 Flash → transcribe audio
    │     ├── Gemini 2.5 Flash → function calling loop
    │     ├── Tool execution (mocked)
    │     └── Gemini TTS → WAV audio response
    │
    └── Realtime Mode: WS /ws/realtime
          └── Proxy → Gemini Live API (BidiGenerateContent)
                (bidirectional PCM16 audio streaming)
```

## 🔧 Mocked Tools

| Tool | Description |
|------|-------------|
| `lookup_order` | Get order status, items, tracking |
| `trigger_refund` | Initiate refund for eligible orders |
| `create_support_ticket` | Log complex issues |
| `check_loyalty_points` | Points balance + tier |
| `escalate_to_human` | Hand off to human agent |

## 📦 Demo Data

| Order ID | Status | Refundable |
|----------|--------|-----------|
| ORD-1234 | Delivered | ✅ Yes |
| ORD-5678 | In Transit | ❌ No |
| ORD-9012 | Processing | ❌ No |
| ORD-3456 | Cancelled | ✅ Yes |

Customer IDs: `CUST-001` (Gold, 2450pts) · `CUST-002` (Silver) · `CUST-003` (Bronze) · `CUST-004` (Platinum)

---

## 🏗️ Stack

| Layer | Technology |
|-------|-----------|
| STT | Gemini 2.5 Flash (native multimodal audio) |
| LLM | Gemini 2.5 Flash (function calling) |
| TTS | Gemini 2.5 Flash TTS |
| Realtime | Gemini Live API (`gemini-2.0-flash-live-001`) |
| Backend | FastAPI + uvicorn (Python) |
| Frontend | React + Vite |

## 📁 Project Structure
```
voice realtime/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── agent.py             # Classic pipeline
│   ├── realtime_proxy.py    # Gemini Live API proxy
│   ├── tools.py             # Mocked tool layer + schemas
│   ├── router_api.py        # REST routes
│   └── router_ws.py         # WebSocket route
├── frontend/
│   └── src/
│       ├── App.jsx          # Main dashboard
│       ├── components/      # VoiceOrb, TranscriptPanel, ToolCallLog, OrderCard
│       └── hooks/           # useAudioRecorder, useRealtimeSession
├── .env.example
├── requirements.txt
└── start.ps1
```
