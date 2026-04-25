"""JARVIS — Voice AI Assistant server."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import signal
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from google import genai
from google.genai import types as genai_types
import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from actions import get_volume, open_app, open_chrome, open_terminal, set_volume
from browser import Browser
from keyword_router import match as keyword_match
from memory import Memory
from planner import Planner
from work_mode import WorkMode

# ── Bootstrap ──────────────────────────────────────────────────────────────────

load_dotenv()

memory = Memory()
browser = Browser()
work_mode = WorkMode()
planner = Planner(work_mode)

# ── Gemini ─────────────────────────────────────────────────────────────────────

_GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
_genai_client = genai.Client(api_key=_GOOGLE_API_KEY) if _GOOGLE_API_KEY else None

_SYSTEM_PROMPT_TEMPLATE = """\
You are JARVIS, a British AI butler assistant.
You are helpful, precise, and slightly formal.
Address the user as "{address}".
Keep responses concise — this is voice output, 2-3 sentences maximum.
Current date/time: {datetime}

Known facts about the user:
{facts}

You have these capabilities. Use action tags only when genuinely needed, \
at most one per response:

[ACTION:SEARCH:your search query]   – Search the web
[ACTION:BROWSE:https://url.com]     – Visit a URL and extract content
[ACTION:TERMINAL:optional command]  – Open Terminal
[ACTION:CHROME:https://url.com]     – Open URL in Chrome
[ACTION:APP:AppName]                – Open an application
[ACTION:VOLUME:50]                  – Set system volume 0-100
[ACTION:PLAN:task description]      – Start planning a development task
[ACTION:REMEMBER:key=value]         – Save a fact about the user
[ACTION:FORGET:key]                 – Remove a saved fact
[ACTION:TASKS]                      – List current tasks
[ACTION:TASK_DONE:id]               – Mark task as done

Never fabricate action results. If you are unsure, say so.\
"""

ACTION_RE = re.compile(r"\[ACTION:(\w+)(?::([^\]]*))?\]")

# ── In-memory state ────────────────────────────────────────────────────────────

_settings: dict[str, str] = {
    "user_name": os.getenv("USER_NAME", ""),
    "voice_id": os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"),
    "volume": "80",
}
_active_sessions: set[str] = set()
_last_responses: dict[str, str] = {}
_interrupt_flags: dict[str, bool] = {}
_connected_ws: list[WebSocket] = []

# ── Helpers ────────────────────────────────────────────────────────────────────


def _build_system_prompt() -> str:
    facts = memory.get_facts()
    facts_str = "\n".join(f"- {k}: {v}" for k, v in facts.items()) or "None"
    address = _settings.get("user_name") or "sir"
    return _SYSTEM_PROMPT_TEMPLATE.format(
        address=address,
        datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
        facts=facts_str,
    )


def _to_gemini_contents(messages: list[dict]) -> list[genai_types.Content]:
    contents = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(
            genai_types.Content(role=role, parts=[genai_types.Part(text=msg["content"])])
        )
    return contents


def _is_echo(user_text: str, last_response: str, threshold: float = 0.7) -> bool:
    if not last_response or not user_text:
        return False
    u_words = set(user_text.lower().split())
    r_words = set(last_response.lower().split())
    if not u_words:
        return False
    return len(u_words & r_words) / len(u_words) >= threshold


async def _speak(text: str, send_fn) -> None:
    """TTS 합성 → afplay로 직접 재생 → 상태 신호 전송."""
    audio_bytes = await _synthesize(text)
    await send_fn({"type": "status", "state": "speaking"})
    if audio_bytes:
        tmp = "/tmp/jarvis_speak.wav"
        Path(tmp).write_bytes(audio_bytes)
        proc = await asyncio.create_subprocess_exec(
            "afplay", tmp, stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
    await send_fn({"type": "status", "state": "idle"})


async def _synthesize(text: str) -> bytes | None:
    el_key = os.getenv("ELEVENLABS_API_KEY", "")
    voice_id = _settings.get("voice_id", "JBFqnCBsd6RMkjVDRZzb")

    if el_key:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    headers={
                        "xi-api-key": el_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "text": text,
                        "model_id": "eleven_turbo_v2",
                        "voice_settings": {
                            "stability": 0.5,
                            "similarity_boost": 0.75,
                        },
                    },
                )
                if resp.status_code == 200:
                    return resp.content
        except Exception:
            pass

    # Fallback — macOS say + afconvert (built-in, no ffmpeg needed)
    aiff = "/tmp/jarvis_say.aiff"
    wav = "/tmp/jarvis_say.wav"
    safe = text.replace('"', "'")
    try:
        say = await asyncio.create_subprocess_exec(
            "say", "-v", "Daniel", "-o", aiff, safe,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await say.wait()

        conv = await asyncio.create_subprocess_exec(
            "afconvert", "-f", "WAVE", "-d", "LEI16@22050", aiff, wav,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await conv.wait()

        target = wav if Path(wav).exists() else aiff
        return Path(target).read_bytes()
    except Exception:
        return None


async def _dispatch_action(
    name: str, args: str | None, session_id: str
) -> str:
    try:
        match name:
            case "SEARCH":
                return await browser.search_web(args or "")
            case "BROWSE":
                return await browser.visit_url(args or "")
            case "TERMINAL":
                return await open_terminal(args or None)
            case "CHROME":
                return await open_chrome(args or None)
            case "APP":
                return await open_app(args or "")
            case "VOLUME":
                return await set_volume(int(args or "50"))
            case "PLAN":
                return await planner.start(session_id, args or "")
            case "REMEMBER":
                if args and "=" in args:
                    k, v = args.split("=", 1)
                    memory.add_fact(k.strip(), v.strip())
                    return f"Remembered: {k.strip()} = {v.strip()}"
                return "Invalid format — use key=value"
            case "FORGET":
                memory.delete_fact(args or "")
                return f"Forgotten: {args}"
            case "TASKS":
                tasks = memory.get_tasks()
                if not tasks:
                    return "No tasks."
                return "\n".join(
                    f"{t['id']}. [{t['status']}] {t['title']}" for t in tasks
                )
            case "TASK_DONE":
                memory.update_task(int(args or "0"), "done")
                return f"Task {args} marked as done."
            case _:
                return f"Unknown action: {name}"
    except Exception as exc:
        return f"Action failed: {exc}"


async def _parse_and_dispatch(
    response_text: str, session_id: str
) -> tuple[str, list[dict]]:
    actions: list[dict] = []
    clean = response_text

    for m in ACTION_RE.finditer(response_text):
        action_name = m.group(1)
        action_args = m.group(2)
        result = await _dispatch_action(action_name, action_args, session_id)
        actions.append({"name": action_name, "args": action_args, "result": result})
        clean = clean.replace(m.group(0), "")

    return clean.strip(), actions


_SHUTDOWN_KEYWORDS = {"종료", "종료해", "종료해줘", "시스템 종료", "꺼줘", "종료하자"}


async def _shutdown_all(delay: float = 1.5) -> None:
    await asyncio.sleep(delay)
    pid_file = Path("data/pids.txt")
    if pid_file.exists():
        for pid in pid_file.read_text().split():
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
        pid_file.unlink(missing_ok=True)
    os.kill(os.getpid(), signal.SIGTERM)


async def _shutdown_if_empty() -> None:
    await asyncio.sleep(5)
    if not _connected_ws:
        print("[SHUTDOWN] No active connections. Shutting down.")
        await _shutdown_all(delay=0)


async def _voiced_summary(raw_info: str) -> str:
    if not _genai_client:
        return raw_info[:200]
    prompt = (
        f"Here is some information:\n{raw_info[:600]}\n\n"
        "Give a concise 1-2 sentence spoken summary."
    )
    try:
        resp = await asyncio.to_thread(
            _genai_client.models.generate_content,
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        return resp.text.strip()
    except Exception:
        return raw_info[:200]


# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await browser.start()
    print("JARVIS server ready — https://localhost:8340")
    yield
    await browser.stop()


# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── REST API ───────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/status")
async def status() -> dict:
    return {"active_sessions": len(_active_sessions)}


@app.get("/api/memory/facts")
async def get_facts() -> dict:
    return memory.get_facts()


class FactBody(BaseModel):
    key: str
    value: str


@app.post("/api/memory/facts")
async def post_fact(body: FactBody) -> dict:
    memory.add_fact(body.key, body.value)
    return {"ok": True}


@app.delete("/api/memory/facts/{key}")
async def delete_fact(key: str) -> dict:
    memory.delete_fact(key)
    return {"ok": True}


@app.get("/api/memory/conversations/{session_id}")
async def get_conversations(session_id: str) -> list:
    return memory.get_context(session_id, limit=50)


@app.delete("/api/memory/conversations/{session_id}")
async def clear_conversations(session_id: str) -> dict:
    memory.clear_session(session_id)
    return {"ok": True}


@app.get("/api/tasks")
async def get_tasks(status: str | None = None) -> list:
    return memory.get_tasks(status)


class TaskBody(BaseModel):
    title: str
    description: str = ""


@app.post("/api/tasks")
async def post_task(body: TaskBody) -> dict:
    task_id = memory.add_task(body.title, body.description)
    return {"id": task_id}


class TaskUpdateBody(BaseModel):
    status: str


@app.patch("/api/tasks/{task_id}")
async def patch_task(task_id: int, body: TaskUpdateBody) -> dict:
    memory.update_task(task_id, body.status)
    return {"ok": True}


@app.get("/api/settings")
async def get_settings() -> dict:
    return _settings


class SettingBody(BaseModel):
    key: str
    value: str


@app.post("/api/settings")
async def post_setting(body: SettingBody) -> dict:
    _settings[body.key] = body.value
    return {"ok": True}


@app.post("/api/wake")
async def wake() -> dict:
    # 연결된 모든 프론트엔드에 wake 신호 브로드캐스트
    msg = json.dumps({"type": "wake"})
    dead: list[WebSocket] = []
    for ws in _connected_ws:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connected_ws.remove(ws)
    return {"ok": True, "notified": len(_connected_ws)}


# ── WebSocket ──────────────────────────────────────────────────────────────────


@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket) -> None:
    await ws.accept()
    _connected_ws.append(ws)
    session_id: str | None = None

    async def send(obj: dict) -> None:
        await ws.send_text(json.dumps(obj))

    async def _greet() -> None:
        await asyncio.sleep(0.5)
        address = _settings.get("user_name", "").strip() or "Master"
        greeting = f"Hello {address}."
        await _speak(greeting, send)

    asyncio.create_task(_greet())

    try:
        while True:
            raw = await ws.receive_text()
            msg: dict = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "ping":
                await send({"type": "pong"})
                continue

            if msg_type == "bye":
                break

            if msg_type == "interrupt":
                if session_id:
                    _interrupt_flags[session_id] = True
                continue

            if msg_type == "settings_update":
                _settings[msg.get("key", "")] = msg.get("value", "")
                continue

            if msg_type != "speech":
                continue

            session_id = msg.get("session_id", "default")
            user_text = msg.get("text", "").strip()
            print(f"[SPEECH] session={session_id} text={user_text!r}")
            if not user_text:
                continue

            _active_sessions.add(session_id)
            _interrupt_flags[session_id] = False

            if user_text in _SHUTDOWN_KEYWORDS:
                farewell = "Shutting down. Goodbye, sir."
                await _speak(farewell, send)
                await send({"type": "shutdown"})
                asyncio.create_task(_shutdown_all())
                break

            if _is_echo(user_text, _last_responses.get(session_id, "")):
                _active_sessions.discard(session_id)
                continue


            await send({"type": "status", "state": "thinking"})

            try:
                # ── Keyword shortcut (Gemini 스킵) ────────────────────────
                address = _settings.get("user_name", "") or "Master"
                keyword_result = await keyword_match(
                    user_text, address=address,
                    get_tasks_fn=memory.get_tasks,
                    search_fn=browser.search_web,
                )
                if keyword_result:
                    clean_text, actions = keyword_result
                    for action in actions:
                        await send({"type": "action", "name": action["name"], "result": action["result"]})
                        if (
                            action["name"] in ("SEARCH", "BROWSE")
                            and action["result"]
                            and not clean_text
                        ):
                            clean_text = await _voiced_summary(action["result"])
                    if not clean_text:
                        clean_text = "Done, sir."
                    memory.add_message(session_id, "user", user_text)
                    memory.add_message(session_id, "assistant", clean_text)
                    _last_responses[session_id] = clean_text
                    _active_sessions.discard(session_id)
                    await _speak(clean_text, send)
                    continue

                # ── Generate response ──────────────────────────────────────
                if not _GOOGLE_API_KEY or not _genai_client:
                    raise RuntimeError("GOOGLE_API_KEY is not set in .env")

                if planner.is_planning(session_id):
                    response_text = await planner.answer(session_id, user_text)
                else:
                    context = memory.get_context(session_id, limit=20)
                    contents = _to_gemini_contents(context)
                    contents.append(
                        genai_types.Content(role="user", parts=[genai_types.Part(text=user_text)])
                    )
                    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
                    gemini_resp = await asyncio.to_thread(
                        _genai_client.models.generate_content,
                        model=model_name,
                        contents=contents,
                        config=genai_types.GenerateContentConfig(
                            system_instruction=_build_system_prompt(),
                            max_output_tokens=250,
                            temperature=0.7,
                        ),
                    )
                    response_text = gemini_resp.text

                # ── Parse & dispatch actions ───────────────────────────────
                clean_text, actions = await _parse_and_dispatch(
                    response_text, session_id
                )

                for action in actions:
                    await send(
                        {
                            "type": "action",
                            "name": action["name"],
                            "result": action["result"],
                        }
                    )
                    # For informational actions, generate a voiced summary
                    if (
                        action["name"] in ("SEARCH", "BROWSE", "TASKS")
                        and action["result"]
                        and not clean_text
                    ):
                        clean_text = await _voiced_summary(action["result"])

                if not clean_text:
                    clean_text = "Done, sir."

                # ── Persist ────────────────────────────────────────────────
                memory.add_message(session_id, "user", user_text)
                memory.add_message(session_id, "assistant", clean_text)
                memory.prune_old_messages(session_id)
                _last_responses[session_id] = clean_text

                if _interrupt_flags.get(session_id):
                    await send({"type": "status", "state": "idle"})
                    continue

                await _speak(clean_text, send)

            except Exception as exc:
                print(f"[ERROR] {exc}")
                err_msg = "I'm sorry, sir. I'm having trouble connecting. Please try again."
                await _speak(err_msg, send)
                await send({"type": "error", "message": str(exc)})
            finally:
                _active_sessions.discard(session_id)

    except WebSocketDisconnect:
        if session_id:
            _active_sessions.discard(session_id)
    finally:
        if ws in _connected_ws:
            _connected_ws.remove(ws)
        if not _connected_ws:
            asyncio.create_task(_shutdown_if_empty())


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8340,
        ssl_keyfile="key.pem",
        ssl_certfile="cert.pem",
        log_level="info",
    )
