"""
마이크 진단 도구 — 실시간 소리 크기 확인

실행: python scripts/test_mic.py
종료: Ctrl+C

이 스크립트로 확인할 것:
  1. 마이크가 잡히는지 (권한 문제)
  2. 박수 쳤을 때 실제 RMS 값 → .env JARVIS_CLAP_THRESHOLD 설정에 활용
"""

import time
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000   # 실제 박수 감지와 동일한 샘플레이트
BLOCK_SIZE  = 512

print("마이크 진단 시작. 아무 소리나 내보세요. 종료: Ctrl+C\n")
print(f"{'레벨':>8}  {'미터':<50}  {'상태'}")
print("-" * 70)

peak = 0.0

def callback(indata, frames, t, status):
    global peak
    rms = float(np.sqrt(np.mean(indata ** 2)))
    peak = max(peak, rms)

    # 시각적 미터
    bar_len = int(min(rms / 0.6 * 50, 50))
    bar = "#" * bar_len + "-" * (50 - bar_len)

    if rms < 0.05:
        label = "조용"
    elif rms < 0.15:
        label = "보통"
    elif rms < 0.30:
        label = "큰 소리"
    else:
        label = "*** 매우 큰 소리 ***"

    print(f"\r{rms:8.4f}  [{bar}]  {label:<20}", end="", flush=True)

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
    print(f"\n\n측정 완료.")
    print(f"  최대 감지 값: {peak:.4f}")
    print()
    if peak < 0.01:
        print("마이크가 전혀 감지되지 않았습니다.")
        print("→ macOS 시스템 설정 → 개인정보 보호 및 보안 → 마이크")
        print("  에서 터미널(Terminal) 권한을 허용해주세요.")
    else:
        recommended = round(peak * 0.5, 2)
        print(f"박수 쳤을 때 최대값의 절반을 threshold로 설정하면 됩니다:")
        print(f"  .env 에 추가: JARVIS_CLAP_THRESHOLD={recommended}")

except Exception as e:
    print(f"\n오류: {e}")
    print("→ macOS 시스템 설정 → 개인정보 보호 및 보안 → 마이크")
    print("  에서 터미널 권한을 확인하세요.")
