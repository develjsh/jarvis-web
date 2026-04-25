#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 사전 확인 ────────────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "[오류] 아직 설치가 완료되지 않았습니다."
    echo "       ./setup.sh 를 먼저 실행하세요."
    exit 1
fi

if [ ! -f ".env" ]; then
    echo "[오류] .env 파일이 없습니다."
    echo "       ./setup.sh 를 먼저 실행하세요."
    exit 1
fi

if [ ! -f "key.pem" ] || [ ! -f "cert.pem" ]; then
    echo "[오류] SSL 인증서가 없습니다."
    echo "       ./setup.sh 를 먼저 실행하세요."
    exit 1
fi

GOOGLE_KEY=$(grep "^GOOGLE_API_KEY=" .env | cut -d= -f2 | tr -d ' ')
if [ -z "$GOOGLE_KEY" ]; then
    echo "[오류] .env 파일에 GOOGLE_API_KEY가 입력되지 않았습니다."
    echo "       open -e .env 를 실행해서 API 키를 입력하세요."
    exit 1
fi

# ── 시작 ─────────────────────────────────────────────────────────────────────
source .venv/bin/activate

echo "Starting JARVIS backend..."
python server.py &
BACKEND_PID=$!

echo "Starting JARVIS frontend..."
cd frontend && npm run dev &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

mkdir -p data
echo "$BACKEND_PID $FRONTEND_PID" > data/pids.txt

echo ""
echo "JARVIS is running."
echo "  Backend PID : $BACKEND_PID"
echo "  Frontend PID: $FRONTEND_PID"
echo ""
echo "Ctrl+C to stop."

(sleep 3 && open http://localhost:5173) &

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; rm -f data/pids.txt; echo "JARVIS stopped."; exit' INT TERM

wait $BACKEND_PID $FRONTEND_PID
