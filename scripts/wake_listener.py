"""
JARVIS Wake Listener — 박수 두 번으로 JARVIS 활성화

실행: python scripts/wake_listener.py
종료: Ctrl+C
"""

import sys
import time
from pathlib import Path

import httpx
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
import os

# .env는 프로젝트 루트에 있음
load_dotenv(Path(__file__).parent.parent / ".env")

WAKE_URL   = os.getenv("JARVIS_WAKE_URL", "https://localhost:8340/api/wake")
THRESHOLD  = float(os.getenv("JARVIS_CLAP_THRESHOLD", "0.30"))
SAMPLE_RATE = 44100
BLOCK_SIZE  = 1024   # ~23ms per block


class ClapDetector:
    """
    더블-클랩 감지 상태 머신.

    동작:
      - 첫 번째 클랩(큰 소리 짧게) 감지 → 타이머 시작
      - 0.15s ~ 0.8s 안에 두 번째 클랩 → wake 트리거
      - 타이머 초과 → 리셋
    """

    DOUBLE_CLAP_WINDOW = 0.8   # 첫 박수 후 이 시간 안에 두 번째가 와야 함 (초)
    MIN_GAP            = 0.15  # 두 박수 사이 최소 간격 (초)
    MAX_CLAP_DURATION  = 0.20  # 클랩으로 인정하는 최대 소리 길이 (초)
    COOLDOWN           = 1.2   # 트리거 후 무시 시간 (초)

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold
        self._above = False
        self._clap_start = 0.0
        self._first_clap_at = 0.0
        self._waiting_second = False
        self._cooldown_until = 0.0

    def feed(self, rms: float) -> bool:
        """오디오 블록 RMS를 입력받아 더블클랩이 감지되면 True 반환."""
        now = time.monotonic()

        # 쿨다운 중
        if now < self._cooldown_until:
            return False

        triggered = False

        if rms > self.threshold and not self._above:
            # 소리 시작
            self._above = True
            self._clap_start = now

        elif rms <= self.threshold and self._above:
            # 소리 끝
            self._above = False
            duration = now - self._clap_start

            if duration <= self.MAX_CLAP_DURATION:
                # 유효한 클랩
                if not self._waiting_second:
                    # 첫 번째 클랩
                    self._first_clap_at = now
                    self._waiting_second = True
                    _print("clap 1")
                else:
                    gap = now - self._first_clap_at
                    if self.MIN_GAP < gap < self.DOUBLE_CLAP_WINDOW:
                        # 두 번째 클랩 — 트리거!
                        _print("clap 2 → WAKE")
                        triggered = True
                        self._cooldown_until = now + self.COOLDOWN
                    # 타이밍이 안 맞으면 두 번째 클랩을 새로운 첫 번째로 처리
                    self._waiting_second = False

        # 윈도우 만료 리셋
        if self._waiting_second and (now - self._first_clap_at) > self.DOUBLE_CLAP_WINDOW:
            _print("window expired, reset")
            self._waiting_second = False

        return triggered


def _print(msg: str) -> None:
    print(f"[wake] {msg}", flush=True)


def _trigger_wake() -> None:
    try:
        with httpx.Client(verify=False, timeout=5) as client:
            client.post(WAKE_URL)
        _print("wake signal sent")
    except Exception as exc:
        _print(f"failed to send wake: {exc}")


def main() -> None:
    detector = ClapDetector(threshold=THRESHOLD)

    print(f"JARVIS Wake Listener 시작")
    print(f"  임계값(threshold): {THRESHOLD}")
    print(f"  박수 두 번 → JARVIS 활성화")
    print(f"  종료: Ctrl+C\n")

    def callback(indata: np.ndarray, frames: int, t, status) -> None:  # type: ignore[no-untyped-def]
        rms = float(np.sqrt(np.mean(indata ** 2)))
        if detector.feed(rms):
            _trigger_wake()

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            channels=1,
            dtype="float32",
            callback=callback,
        ):
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nWake listener 종료.")
    except Exception as exc:
        print(f"오류: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
