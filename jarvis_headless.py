"""
JARVIS Headless — 브라우저 없이 완전 백그라운드 실행

실행: python jarvis_headless.py   ← 이것 하나로 전부 실행됨
종료: Ctrl+C

흐름:
  [시작] server.py 자동 실행 → 헬스체크 통과 대기
  박수 두 번 → 마이크 녹음 (묵음 감지로 자동 종료)
  → Google STT → server.py WebSocket → ElevenLabs/say TTS → afplay 재생
  → 대기 상태로 복귀
  [종료] server.py 자동 종료
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import uuid
import wave
from pathlib import Path

import httpx
import numpy as np
import sounddevice as sd
import speech_recognition as sr
import websockets
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── 설정 ───────────────────────────────────────────────────────────────────────

WS_URL          = "wss://localhost:8340/ws/voice"
SAMPLE_RATE     = 16000   # Google STT 권장 샘플레이트
BLOCK_SIZE      = 512
CLAP_THRESHOLD  = float(os.getenv("JARVIS_CLAP_THRESHOLD", "0.15"))
STT_LANGUAGE    = os.getenv("STT_LANGUAGE", "ko-KR")  # 한국어 기본값

# 녹음 VAD 설정
SPEECH_THRESHOLD  = 0.015   # 이 이상이면 말하는 중
SILENCE_SECS      = 1.5     # 이 시간 동안 묵음이면 녹음 종료
MAX_RECORD_SECS   = 12.0    # 최대 녹음 시간


# ── 상태 출력 ──────────────────────────────────────────────────────────────────

def status(msg: str) -> None:
    print(f"\r\033[K[JARVIS] {msg}", end="", flush=True)

def log(msg: str) -> None:
    print(f"\n[JARVIS] {msg}", flush=True)


# ── 박수 감지 ──────────────────────────────────────────────────────────────────

class ClapDetector:
    """
    상승 엣지 기반 더블클랩 감지.
    - threshold를 넘는 순간만 체크 (지속 시간 무관)
    - 히스테리시스로 잔향에 의한 오감지 방지
    """
    DOUBLE_CLAP_WINDOW = 1.2   # 첫 박수 후 두 번째까지 허용 시간 (초)
    MIN_GAP            = 0.10  # 두 박수 사이 최소 간격 (초)
    COOLDOWN           = 1.5   # 트리거 후 무시 시간 (초)
    HYSTERESIS         = 0.5   # 임계값 * 이 비율 이하로 내려가야 다음 감지 허용

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold
        self._above = False
        self._first_clap_at = 0.0
        self._waiting_second = False
        self._cooldown_until = 0.0

    def feed(self, rms: float) -> bool:
        now = time.monotonic()

        if now < self._cooldown_until:
            return False

        # 윈도우 만료 리셋
        if self._waiting_second and (now - self._first_clap_at) > self.DOUBLE_CLAP_WINDOW:
            self._waiting_second = False

        # 히스테리시스: 완전히 내려가야 다음 상승 감지
        if self._above and rms < self.threshold * self.HYSTERESIS:
            self._above = False

        # 상승 엣지 감지
        if rms >= self.threshold and not self._above:
            self._above = True

            if not self._waiting_second:
                # 첫 번째 클랩
                self._first_clap_at = now
                self._waiting_second = True
                status("clap 1 감지... 한 번 더")
            else:
                gap = now - self._first_clap_at
                if gap >= self.MIN_GAP:
                    # 두 번째 클랩 — 트리거!
                    self._waiting_second = False
                    self._cooldown_until = now + self.COOLDOWN
                    return True
                # MIN_GAP 이내면 잔향으로 간주, 무시

        return False


# ── 마이크 녹음 (VAD) ──────────────────────────────────────────────────────────

def record_with_vad() -> np.ndarray:
    """묵음 감지로 자동 종료되는 녹음. int16 numpy 배열 반환."""
    chunks: list[np.ndarray] = []
    silence_blocks_needed = int(SILENCE_SECS * SAMPLE_RATE / BLOCK_SIZE)
    max_blocks = int(MAX_RECORD_SECS * SAMPLE_RATE / BLOCK_SIZE)
    silence_count = 0
    started_speaking = False

    status("듣는 중...")

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE,
        channels=1,
        dtype="float32",
    ) as stream:
        for _ in range(max_blocks):
            chunk, _ = stream.read(BLOCK_SIZE)
            chunks.append(chunk.copy())
            rms = float(np.sqrt(np.mean(chunk ** 2)))

            if rms >= SPEECH_THRESHOLD:
                started_speaking = True
                silence_count = 0
            elif started_speaking:
                silence_count += 1
                if silence_count >= silence_blocks_needed:
                    break

    audio = np.concatenate(chunks).flatten()
    return (audio * 32767).astype(np.int16)


def audio_to_wav_bytes(audio: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)   # int16 = 2 bytes
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


def speech_to_text(audio: np.ndarray) -> str | None:
    wav_bytes = audio_to_wav_bytes(audio)
    recognizer = sr.Recognizer()
    audio_data = sr.AudioData(wav_bytes, SAMPLE_RATE, 2)
    try:
        status("음성 인식 중...")
        text = recognizer.recognize_google(audio_data)
        return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError as exc:
        log(f"STT 오류: {exc}")
        return None


# ── 오디오 재생 ────────────────────────────────────────────────────────────────

def play_audio(audio_b64: str) -> None:
    if not audio_b64:
        return
    try:
        data = base64.b64decode(audio_b64)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(data)
            tmp = f.name
        subprocess.run(["afplay", tmp], check=False)
        Path(tmp).unlink(missing_ok=True)
    except Exception as exc:
        log(f"재생 오류: {exc}")


# ── WebSocket 클라이언트 ───────────────────────────────────────────────────────

def _make_ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def send_and_receive(text: str, session_id: str) -> tuple[str, str]:
    """
    서버에 텍스트 전송 후 response 메시지 수신.
    반환: (응답 텍스트, base64 오디오)
    """
    ssl_ctx = _make_ssl_ctx()

    async def _communicate() -> tuple[str, str]:
        async with websockets.connect(WS_URL, ssl=ssl_ctx, open_timeout=10) as ws:
            await ws.send(json.dumps({
                "type": "speech",
                "text": text,
                "session_id": session_id,
            }))

            response_text = ""
            audio_b64 = ""

            async for raw in ws:
                msg = json.loads(raw)
                t = msg.get("type")

                if t == "response":
                    response_text = msg.get("text", "")
                    audio_b64 = msg.get("audio", "")
                    break
                elif t == "error":
                    log(f"서버 오류: {msg.get('message')}")
                    break
                elif t == "status" and msg.get("state") == "idle":
                    break

            return response_text, audio_b64

    try:
        return await asyncio.wait_for(_communicate(), timeout=40)
    except asyncio.TimeoutError:
        raise RuntimeError("서버 응답 시간 초과 (40초)")


# ── 서버 프로세스 관리 ────────────────────────────────────────────────────────────

_HEALTH_URL = "https://localhost:8340/api/health"
_SERVER_SCRIPT = Path(__file__).parent / "server.py"


def _start_server() -> subprocess.Popen:  # type: ignore[type-arg]
    """server.py를 백그라운드 서브프로세스로 실행."""
    proc = subprocess.Popen(
        [sys.executable, str(_SERVER_SCRIPT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(Path(__file__).parent),
    )
    return proc


def _wait_for_server(timeout: float = 20.0) -> bool:
    """서버가 응답할 때까지 최대 timeout 초 대기. 성공하면 True."""
    deadline = time.monotonic() + timeout
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    while time.monotonic() < deadline:
        try:
            r = httpx.get(_HEALTH_URL, verify=False, timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


# ── macOS 알림 ─────────────────────────────────────────────────────────────────

def notify(title: str, msg: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{msg}" with title "{title}"'],
            check=False,
            capture_output=True,
        )
    except Exception:
        pass


# ── 메인 루프 ──────────────────────────────────────────────────────────────────

async def main() -> None:
    detector = ClapDetector(threshold=CLAP_THRESHOLD)
    session_id = str(uuid.uuid4())
    triggered = asyncio.Event()
    loop = asyncio.get_event_loop()

    def audio_callback(
        indata: np.ndarray, frames: int, t: object, status_flag: object
    ) -> None:
        rms = float(np.sqrt(np.mean(indata ** 2)))
        if detector.feed(rms):
            loop.call_soon_threadsafe(triggered.set)

    print("=" * 48)
    print("  JARVIS Headless 실행 중")
    print(f"  박수 두 번으로 활성화 (감도: {CLAP_THRESHOLD})")
    print("  종료: Ctrl+C")
    print("=" * 48)
    status("대기 중 (박수 두 번)")

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            channels=1,
            dtype="float32",
            callback=audio_callback,
        ):
            while True:
                await triggered.wait()
                triggered.clear()

                notify("JARVIS", "듣고 있습니다...")

                # 인식 실패 시 최대 3회 자동 재시도 (박수 불필요)
                text = None
                for attempt in range(3):
                    audio = await asyncio.to_thread(record_with_vad)

                    if len(audio) < SAMPLE_RATE * 0.3:
                        status("너무 짧습니다. 다시 말씀해주세요...")
                        await asyncio.sleep(0.5)
                        continue

                    text = await asyncio.to_thread(speech_to_text, audio)
                    if text:
                        break

                    remaining = 2 - attempt
                    if remaining > 0:
                        status(f"인식 실패. 다시 말씀해주세요... ({remaining}회 남음)")
                        await asyncio.sleep(0.5)

                if not text:
                    status("인식 실패. 박수 두 번으로 다시 시작하세요.")
                    await asyncio.sleep(1)
                    status("대기 중 (박수 두 번)")
                    continue

                log(f"인식: \"{text}\"")
                status("생각 중...")

                try:
                    resp_text, audio_b64 = await send_and_receive(text, session_id)
                    if resp_text:
                        log(f"JARVIS: \"{resp_text}\"")
                        status("응답 재생 중...")
                        await asyncio.to_thread(play_audio, audio_b64)

                except Exception as exc:
                    log(f"서버 연결 오류: {exc}")

                status("대기 중 (박수 두 번)")

    except KeyboardInterrupt:
        print("\nJARVIS 종료.")


if __name__ == "__main__":
    # ── 서버 자동 시작 ──────────────────────────────────────────────────────────
    print("=" * 48)
    print("  JARVIS 시작 중...")
    print("=" * 48)

    print("[1/2] server.py 실행 중...", flush=True)
    server_proc = _start_server()

    print("[2/2] 서버 응답 대기 중...", flush=True)
    if not _wait_for_server(timeout=20):
        print("오류: 서버가 20초 안에 응답하지 않습니다.")
        print("  - .env 파일에 GOOGLE_API_KEY가 입력됐는지 확인하세요.")
        print("  - key.pem / cert.pem 파일이 있는지 확인하세요.")
        server_proc.terminate()
        sys.exit(1)

    print("서버 준비 완료.\n", flush=True)

    # ── 헤드리스 루프 실행 ─────────────────────────────────────────────────────
    try:
        asyncio.run(main())
    finally:
        server_proc.terminate()
        server_proc.wait()
        print("서버 종료 완료.")
