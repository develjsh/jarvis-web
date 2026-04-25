#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "================================================"
echo "  JARVIS macOS 설치 프로그램"
echo "================================================"
echo ""

# ── 1. Python 확인 ────────────────────────────────────────────────────────────
echo "[1/6] Python 확인 중..."
if ! command -v python3 &>/dev/null; then
    echo ""
    echo "[오류] Python3이 설치되지 않았습니다."
    echo "       brew install python3  또는"
    echo "       https://www.python.org 에서 Python 3.11 이상 설치 후 다시 실행하세요."
    echo ""
    exit 1
fi
PYVER=$(python3 --version 2>&1 | awk '{print $2}')
PYMAJOR=$(echo "$PYVER" | cut -d. -f1)
PYMINOR=$(echo "$PYVER" | cut -d. -f2)
if [ "$PYMAJOR" -lt 3 ] || ([ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 11 ]); then
    echo "[오류] Python 3.11 이상이 필요합니다. 현재: $PYVER"
    exit 1
fi
echo "    Python $PYVER 확인됨"

# ── 2. Node.js 확인 ──────────────────────────────────────────────────────────
echo "[2/6] Node.js 확인 중..."
if ! command -v node &>/dev/null; then
    echo ""
    echo "[오류] Node.js가 설치되지 않았습니다."
    echo "       brew install node  또는"
    echo "       https://nodejs.org 에서 Node.js 18 이상 설치 후 다시 실행하세요."
    echo ""
    exit 1
fi
NODEVER=$(node --version)
echo "    Node.js $NODEVER 확인됨"

# ── 3. 가상환경 생성 ─────────────────────────────────────────────────────────
echo "[3/6] Python 가상환경 생성 중..."
if [ -d ".venv" ]; then
    echo "    기존 가상환경 발견, 재사용합니다."
else
    python3 -m venv .venv
    echo "    가상환경 생성 완료"
fi

# ── 4. Python 패키지 설치 ────────────────────────────────────────────────────
echo "[4/6] Python 패키지 설치 중... (시간이 걸릴 수 있습니다)"
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
if [ $? -ne 0 ]; then
    echo "[오류] 패키지 설치 실패. 인터넷 연결을 확인하세요."
    exit 1
fi
echo "    패키지 설치 완료"

echo "    Playwright 브라우저 설치 중..."
playwright install chromium --quiet 2>/dev/null \
    || echo "    [경고] Playwright 브라우저 설치 실패 (웹 검색 기능 비활성화됨)"

# ── 5. 프론트엔드 설치 ──────────────────────────────────────────────────────
echo "[5/6] 프론트엔드 패키지 설치 중..."
cd frontend
npm install --silent
if [ $? -ne 0 ]; then
    echo "[오류] npm install 실패"
    exit 1
fi
cd ..
echo "    프론트엔드 설치 완료"

# ── 6. SSL 인증서 생성 ──────────────────────────────────────────────────────
echo "[6/6] SSL 인증서 확인/생성 중..."
if [ -f "key.pem" ] && [ -f "cert.pem" ]; then
    echo "    기존 인증서 발견, 재사용합니다."
else
    python scripts/gen_cert.py
    if [ $? -ne 0 ]; then
        echo "[오류] SSL 인증서 생성 실패"
        exit 1
    fi
fi

# ── .env 파일 생성 ────────────────────────────────────────────────────────────
echo ""
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ".env 파일이 생성됐습니다."
else
    echo ".env 파일이 이미 존재합니다."
fi

# ── 완료 ────────────────────────────────────────────────────────────────────
echo ""
echo "================================================"
echo "  설치 완료!"
echo "================================================"
echo ""
echo "다음 단계:"
echo ""
echo "  1. .env 파일을 열어 API 키를 입력하세요:"
echo ""
echo "     open -e .env"
echo ""
echo "     GOOGLE_API_KEY=여기에입력"
echo "     ELEVENLABS_API_KEY=여기에입력  (없으면 macOS say 음성 사용)"
echo ""
echo "  2. API 키 입력 후 실행 방법:"
echo ""
echo "     웹 UI 모드 :  ./start.sh          (브라우저에서 사용)"
echo "     헤드리스 모드:  python jarvis_headless.py  (마이크로 직접 대화)"
echo ""
echo "================================================"
echo ""

read -r -p "지금 바로 .env 파일을 열까요? (y/N): " OPEN_ENV
if [[ "$OPEN_ENV" =~ ^[Yy]$ ]]; then
    open -e .env
fi

echo ""
echo "설치가 완료됐습니다. ./start.sh 를 실행하세요."
echo ""
