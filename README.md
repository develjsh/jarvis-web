# JARVIS — Voice AI Assistant

A local voice AI assistant inspired by Iron Man's JARVIS.  
Speak naturally in Korean or English — JARVIS listens, thinks, and responds with a British accent.

---

## Features

| Category | Details |
|---|---|
| Voice recognition | Web Speech API, bilingual (Korean / English), auto language detection |
| AI brain | Google Gemini 2.5 Flash via streaming WebSocket |
| Text-to-speech | ElevenLabs (George — British accent), fallback to macOS `say` |
| Orb visualization | Three.js particle orb that reacts to audio amplitude |
| Conversation memory | SQLite FTS5 — facts, tasks, and history persist across sessions |
| Keyword routing | Volume, time, app launch, and web search handled without API call |
| Work mode | Runs `claude -p` as a subprocess and streams output to a file |
| Browser control | Playwright-based web search and page reading |
| Planning | Multi-step task planner with subtask tracking |

---

## Requirements

- macOS (TTS playback uses `afplay` / `say`)
- Python 3.11 or later
- Node.js 18 or later
- Google AI Studio API key — [aistudio.google.com](https://aistudio.google.com)
- ElevenLabs API key (optional) — [elevenlabs.io](https://elevenlabs.io)

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/develjsh/jarvis-web.git
cd jarvis-web
```

### 2. Install

```bash
chmod +x setup.sh
./setup.sh
```

`setup.sh` does the following automatically:

- Checks Python 3.11+ and Node.js
- Creates a Python virtual environment (`.venv/`)
- Installs Python packages from `requirements.txt`
- Installs Playwright Chromium (web search feature)
- Runs `npm install` in `frontend/`
- Generates a self-signed SSL certificate (`cert.pem` / `key.pem`)
- Creates `.env` from `.env.example`

### 3. Set API keys

```bash
open -e .env
```

```env
GOOGLE_API_KEY=your_google_ai_studio_key_here
ELEVENLABS_API_KEY=your_elevenlabs_key_here   # optional
USER_NAME=Tony                                 # JARVIS will call you by this name
```

### 4. Run

```bash
./start.sh
```

A browser tab opens automatically at `http://localhost:5173`.  
Click anywhere on the orb to start listening.

### 5. Stop

```bash
./stop.sh
```

---

## How It Works

```
Browser (Web Speech API)
    │  speech text (WebSocket)
    ▼
FastAPI server  ──► Keyword Router (volume / time / apps)
    │
    ▼
Gemini 2.5 Flash (streaming)
    │
    ▼
ElevenLabs TTS  ──► base64 audio ──► afplay (macOS)
    │
    ▼
Browser  ◄── status / transcript messages (WebSocket)
```

- The browser uses the **Web Speech API** for speech recognition — no microphone data is sent to a third-party service.
- The FastAPI backend handles all AI and TTS calls.
- Audio is played server-side via `afplay`; the browser only shows status messages.
- Conversation context is stored locally in `data/jarvis.db` (SQLite).

---

## Voice Commands (Examples)

| What you say | What happens |
|---|---|
| "볼륨 50으로 해줘" | Sets macOS system volume to 50 |
| "지금 몇 시야?" | Returns current time without API call |
| "크롬 열어줘" | Opens Google Chrome |
| "구글에서 파이썬 검색해줘" | Playwright web search |
| "오늘 할 일 추가해줘" | Adds a task to the planner |
| "작업 모드 시작해줘" | Starts Work Mode (runs Claude CLI) |
| Anything else | Sent to Gemini 2.5 Flash |

---

## Configuration (`.env`)

| Key | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | Google AI Studio key |
| `ELEVENLABS_API_KEY` | No | ElevenLabs key (falls back to `say`) |
| `ELEVENLABS_VOICE_ID` | No | Default: `JBFqnCBsd6RMkjVDRZzb` (George) |
| `USER_NAME` | No | Name JARVIS uses to address you (default: `Master`) |
| `GEMINI_MODEL` | No | Default: `gemini-2.5-flash` |
| `JARVIS_AMBIENT_ENABLED` | No | `true` to play ambient sounds |
| `JARVIS_AMBIENT_DIR` | No | Path to ambient audio files |

---

## Project Structure

```
jarvis-web/
├── server.py           # FastAPI WebSocket server + Gemini streaming
├── actions.py          # System actions (volume, app launch)
├── browser.py          # Playwright web search
├── keyword_router.py   # Fast local command matching
├── memory.py           # SQLite conversation memory
├── planner.py          # Multi-step task planning
├── work_mode.py        # Claude CLI subprocess runner
├── jarvis_headless.py  # CLI mode (no browser)
├── requirements.txt
├── setup.sh            # One-command installer
├── start.sh            # Start backend + frontend
├── stop.sh             # Stop all processes
├── scripts/
│   └── gen_cert.py     # Self-signed SSL certificate generator
├── frontend/
│   ├── index.html
│   ├── src/
│   │   ├── main.ts     # App entry — WebSocket, UI, orb control
│   │   ├── voice.ts    # VoiceManager — Web Speech API + audio playback
│   │   ├── orb.ts      # Three.js particle orb
│   │   └── style.css
│   ├── package.json
│   └── vite.config.ts  # Dev server + WebSocket proxy
└── .env.example
```

---

## Headless Mode (no browser)

```bash
source .venv/bin/activate
python jarvis_headless.py
```

Uses `sounddevice` for microphone input and the same backend pipeline.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

This project is for personal and educational use.  
API usage (Google AI Studio, ElevenLabs) is subject to each provider's own terms of service.
