# JARVIS — 전체 설계 문서

> 이 문서를 읽으면 재설계 없이 바로 구현 시작 가능.
> 민감 데이터 접근(Calendar, Mail, Notes), 어필리에이트 링크, 강제 홍보 문구 모두 제거된 버전.

---

## 디렉토리 구조

```
jarvis/
├── DESIGN.md                  # 이 파일
├── .env                       # API 키 (gitignore)
├── .env.example
├── .gitignore
├── requirements.txt
├── server.py                  # FastAPI 메인 서버 (~600줄)
├── memory.py                  # SQLite 메모리 시스템
├── actions.py                 # 시스템 액션 (Terminal, Chrome)
├── browser.py                 # Playwright 웹 브라우징
├── work_mode.py               # Claude Code CLI 세션 관리
├── planner.py                 # 대화형 작업 계획
├── data/
│   └── ambient/               # (선택) 자연음 파일
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
│       ├── index.html
│       ├── style.css
│       ├── main.ts            # 프론트엔드 상태 머신
│       ├── orb.ts             # Three.js 파티클 오브
│       ├── voice.ts           # Web Speech API + 오디오 재생
│       ├── ws.ts              # WebSocket 클라이언트
│       └── settings.ts        # 설정 패널
├── scripts/
│   └── gen_cert.sh            # SSL 인증서 생성
└── helpers/
```

---

## 아키텍처

```
Microphone
    → Web Speech API (브라우저)
    → WebSocket (JSON)
    → FastAPI server.py (localhost:8340, HTTPS)
        → memory.py (SQLite, 대화 컨텍스트 로드)
        → Gemini 2.0 Flash API (응답 생성, max 250 tokens)
        → [ACTION:X] 파싱 → actions.py / browser.py / work_mode.py / planner.py
        → ElevenLabs TTS → base64 MP3
            (실패 시 → macOS `say -v Daniel` 폴백)
    → WebSocket (base64 오디오)
    → Web Audio API (브라우저 재생)
    → Three.js Orb (오디오 진폭에 반응)
```

---

## 환경 변수 (.env)

```env
GOOGLE_API_KEY=                 # 필수 (aistudio.google.com에서 발급)
ELEVENLABS_API_KEY=             # 필수 (없으면 macOS say 폴백)

# 선택
USER_NAME=                      # JARVIS가 이름으로 호칭
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb   # George (British)
GEMINI_MODEL=gemini-2.0-flash   # 기본값, 변경 불필요
JARVIS_AMBIENT_ENABLED=false
JARVIS_AMBIENT_DIR=
```

---

## 1. memory.py

### 역할
- SQLite (FTS5) 기반 대화 기록, 사실(facts), 작업(tasks) 저장
- DB 파일: `data/jarvis.db`

### 테이블 스키마

```sql
-- 대화 기록 (rolling window)
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,          -- 'user' | 'assistant'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE VIRTUAL TABLE conversations_fts USING fts5(content, content=conversations, content_rowid=id);

-- 장기 사실 (유저가 알려준 정보)
CREATE TABLE facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 작업 목록
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'pending',  -- 'pending' | 'in_progress' | 'done'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 클래스 및 메서드

```python
class Memory:
    def __init__(self, db_path: str = "data/jarvis.db"):
        ...

    def add_message(self, session_id: str, role: str, content: str) -> None:
        # conversations 테이블에 삽입, FTS 동기화

    def get_context(self, session_id: str, limit: int = 20) -> list[dict]:
        # 최근 N개 메시지 반환 → [{"role": "user", "content": "..."}]

    def search(self, query: str, limit: int = 5) -> list[dict]:
        # FTS5 전문 검색

    def add_fact(self, key: str, value: str) -> None:
        # UPSERT (key 중복 시 value 업데이트)

    def get_facts(self) -> dict[str, str]:
        # 전체 facts 딕셔너리 반환

    def delete_fact(self, key: str) -> None:

    def add_task(self, title: str, description: str = "") -> int:
        # 작업 추가, task id 반환

    def get_tasks(self, status: str | None = None) -> list[dict]:

    def update_task(self, task_id: int, status: str) -> None:

    def clear_session(self, session_id: str) -> None:
        # 해당 세션 대화 기록 삭제

    def prune_old_messages(self, session_id: str, keep: int = 50) -> None:
        # 오래된 메시지 정리 (keep 개수만 유지)
```

---

## 2. actions.py

### 역할
- 민감 데이터 없는 시스템 제어 (Terminal, Chrome, 앱 열기)
- AppleScript 사용 (macOS 전용)

### 함수

```python
async def open_terminal(command: str | None = None) -> str:
    # Terminal.app 열기, command 있으면 실행
    # AppleScript: tell app "Terminal" to do script "..."
    # 반환: "Terminal opened" | "Terminal opened with command: ..."

async def open_chrome(url: str | None = None) -> str:
    # Chrome 열기, url 있으면 해당 페이지로
    # 반환: "Chrome opened" | "Chrome opened: <url>"

async def open_app(app_name: str) -> str:
    # AppleScript: tell app "<name>" to activate
    # 반환: "<app_name> opened"

async def set_volume(level: int) -> str:
    # 0-100 → osascript set volume output volume level
    # 반환: "Volume set to <level>"

async def get_volume() -> int:
    # 현재 볼륨 반환

async def run_applescript(script: str) -> str:
    # 범용 AppleScript 실행 (server.py에서 직접 호출용)
    # subprocess.run(["osascript", "-e", script], ...)
```

---

## 3. browser.py

### 역할
- Playwright 비동기 브라우저 (Chromium headless)
- 웹 검색, URL 방문, 텍스트 추출

### 클래스

```python
class Browser:
    def __init__(self):
        self._browser = None
        self._page = None

    async def start(self) -> None:
        # playwright.async_api로 Chromium 실행

    async def stop(self) -> None:

    async def search_web(self, query: str) -> str:
        # DuckDuckGo 검색 → 상위 3개 결과 제목+URL+요약 반환
        # URL: https://html.duckduckgo.com/html/?q=<query>
        # 반환: 요약 텍스트 (500자 이내)

    async def visit_url(self, url: str) -> str:
        # URL 방문 → body 텍스트 추출 (1000자 이내)
        # JS 렌더링 대기: wait_until="networkidle"

    async def take_screenshot(self, url: str) -> str:
        # 스크린샷 → data/screenshot.png 저장
        # 반환: 파일 경로
```

---

## 4. work_mode.py

### 역할
- `claude -p` CLI 서브프로세스로 백그라운드 Claude Code 세션 실행
- 진행 상황 실시간 수집

### 클래스

```python
class WorkMode:
    def __init__(self):
        self._process: asyncio.subprocess.Process | None = None
        self._output_path = "data/.jarvis_output.txt"

    async def start_task(self, prompt: str) -> str:
        # claude -p "<prompt>" > output_path 2>&1 &
        # 반환: "Task started. I will notify you when complete."

    async def continue_task(self, prompt: str) -> str:
        # claude -p --continue "<prompt>"

    async def get_output(self) -> str:
        # output_path 읽기, 마지막 500자 반환

    async def is_running(self) -> bool:

    async def stop_task(self) -> str:
        # 프로세스 종료
```

---

## 5. planner.py

### 역할
- 큰 작업 시작 전 명확화 질문 대화
- 충분한 정보 수집 후 work_mode.py로 전달

### 클래스

```python
class Planner:
    def __init__(self, work_mode: WorkMode):
        self._sessions: dict[str, PlanSession] = {}

    async def start(self, session_id: str, description: str) -> str:
        # 작업 설명 분석 → 첫 번째 명확화 질문 반환
        # ex: "What language or framework would you prefer?"

    async def answer(self, session_id: str, user_answer: str) -> str:
        # 답변 처리 → 다음 질문 또는 계획 확정 후 work_mode.start_task() 호출
        # 질문 최대 3개

    def is_planning(self, session_id: str) -> bool:
```

---

## 6. server.py

### 역할
- FastAPI 메인 서버 (HTTPS, localhost:8340)
- WebSocket `/ws/voice` 핸들러
- REST API
- Gemini 2.0 Flash 호출 + 액션 파싱
- ElevenLabs / macOS say TTS

### 시작 시 초기화 순서

```python
# 1. .env 로드
# 2. Memory() 초기화
# 3. Browser().start() (백그라운드)
# 4. WorkMode() 초기화
# 5. Planner(work_mode) 초기화
# 6. FastAPI app 생성
# 7. SSL: ssl_keyfile=key.pem, ssl_certfile=cert.pem
# 8. uvicorn.run(app, host="0.0.0.0", port=8340, ssl_...)
```

### REST API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/health` | `{"status": "ok"}` |
| GET | `/api/status` | 현재 서버 상태, 활성 세션 수 |
| GET | `/api/memory/facts` | 전체 facts 반환 |
| POST | `/api/memory/facts` | `{"key": "...", "value": "..."}` |
| DELETE | `/api/memory/facts/{key}` | fact 삭제 |
| GET | `/api/memory/conversations/{session_id}` | 대화 기록 |
| DELETE | `/api/memory/conversations/{session_id}` | 세션 초기화 |
| GET | `/api/tasks` | 작업 목록 |
| POST | `/api/tasks` | 작업 추가 |
| PATCH | `/api/tasks/{id}` | 상태 변경 |
| GET | `/api/settings` | 현재 설정 반환 |
| POST | `/api/settings` | 설정 변경 |
| POST | `/api/wake` | 웨이크 트리거 (외부 훅용) |

### WebSocket 메시지 프로토콜

**Client → Server:**
```json
{"type": "speech", "text": "...", "session_id": "uuid4"}
{"type": "ping"}
{"type": "interrupt"}
{"type": "settings_update", "key": "user_name", "value": "Tony"}
```

**Server → Client:**
```json
{"type": "status", "state": "listening|thinking|speaking|idle"}
{"type": "transcript", "text": "...", "final": true}
{"type": "response", "text": "...", "audio": "<base64_mp3>"}
{"type": "action", "name": "SEARCH", "query": "...", "result": "..."}
{"type": "task_update", "status": "started|done", "output": "..."}
{"type": "error", "message": "..."}
{"type": "pong"}
```

### Gemini 2.0 Flash 호출 방식

```python
import google.generativeai as genai

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
model = genai.GenerativeModel(
    model_name=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    system_instruction=SYSTEM_PROMPT,
    generation_config=genai.GenerationConfig(
        max_output_tokens=250,
        temperature=0.7,
    )
)

# 호출 방식 (대화 기록 포함)
chat = model.start_chat(history=gemini_history)  # [{role, parts}] 형식
response = await asyncio.to_thread(chat.send_message, user_text)
response_text = response.text

# memory.get_context() → Gemini history 변환
def to_gemini_history(messages: list[dict]) -> list[dict]:
    # [{"role": "user"|"model", "parts": [{"text": "..."}]}]
    # memory의 "assistant" → Gemini의 "model"로 변환
```

### Gemini 시스템 프롬프트

```
You are JARVIS, a British AI butler assistant.
You are helpful, precise, and slightly formal.
Address the user as "sir" (or by name: {user_name}).
Keep responses short — this is voice output, 2-3 sentences maximum.
Current date/time: {datetime}

Known facts about the user:
{facts}

You have these capabilities (use action tags only when needed, max one per response):
[ACTION:SEARCH:your search query]     - Search the web
[ACTION:BROWSE:https://url.com]       - Visit a URL and extract content
[ACTION:TERMINAL:optional command]    - Open Terminal (run a command)
[ACTION:CHROME:https://url.com]       - Open URL in Chrome
[ACTION:APP:AppName]                  - Open an application
[ACTION:VOLUME:50]                    - Set system volume (0-100)
[ACTION:PLAN:task description]        - Start planning a development task
[ACTION:REMEMBER:key=value]           - Save a fact about the user
[ACTION:FORGET:key]                   - Remove a saved fact
[ACTION:TASKS]                        - List current tasks
[ACTION:TASK_DONE:id]                 - Mark task as done

Never fabricate action results. If unsure, say so.
```

### 액션 파싱 로직

```python
import re

ACTION_PATTERN = re.compile(r'\[ACTION:(\w+)(?::([^\]]*))?\]')

async def parse_and_dispatch(response_text: str, session_id: str) -> tuple[str, list[dict]]:
    # response_text에서 ACTION 태그 추출
    # 태그 제거한 텍스트 + 액션 결과 목록 반환
    actions_taken = []
    clean_text = response_text

    for match in ACTION_PATTERN.finditer(response_text):
        action_name = match.group(1)   # "SEARCH"
        action_args = match.group(2)   # "query string"
        result = await dispatch_action(action_name, action_args, session_id)
        actions_taken.append({"name": action_name, "args": action_args, "result": result})
        clean_text = clean_text.replace(match.group(0), "")

    return clean_text.strip(), actions_taken
```

### TTS 파이프라인

```python
async def synthesize(text: str) -> bytes | None:
    # 1. ElevenLabs 시도
    #    POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
    #    voice_id = env ELEVENLABS_VOICE_ID (기본: JBFqnCBsd6RMkjVDRZzb = George)
    #    model_id = "eleven_turbo_v2" (저지연)
    #    반환: MP3 bytes
    # 2. 실패 시 macOS say 폴백
    #    say -v Daniel -o /tmp/jarvis_say.aiff "<text>"
    #    ffmpeg -i /tmp/jarvis_say.aiff /tmp/jarvis_say.mp3
    #    /tmp/jarvis_say.mp3 읽어서 반환
    # 3. ffmpeg 없으면 aiff 그대로 반환
```

### 에코 필터

```python
def is_echo(user_text: str, last_response: str, threshold: float = 0.7) -> bool:
    # 사용자가 말한 텍스트가 직전 JARVIS 응답과 너무 유사하면 True
    # 간단 구현: 공통 단어 비율로 판단
    # 에코이면 해당 WebSocket 메시지 무시
```

### WebSocket 핸들러 흐름

```
receive message
    → type == "ping" → send pong
    → type == "speech"
        → is_echo 체크 → 에코면 무시
        → send status: "thinking"
        → memory.get_context(session_id) 로드
        → memory.get_facts() 로드
        → Planner.is_planning 체크 → 계획 중이면 planner.answer()
        → 아니면 Gemini 2.0 Flash 호출 (스트리밍 아님, 단건)
        → parse_and_dispatch → clean_text, actions
        → actions 있으면 send action 메시지들
        → memory.add_message(session_id, "user", text)
        → memory.add_message(session_id, "assistant", clean_text)
        → synthesize(clean_text) → audio_bytes
        → send response: {text, audio: base64(audio_bytes)}
        → send status: "idle"
    → type == "interrupt"
        → 현재 TTS 중단 플래그 설정
```

---

## 7. 프론트엔드

### index.html 구조

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JARVIS</title>
  <link rel="stylesheet" href="/src/style.css">
</head>
<body>
  <canvas id="orb-canvas"></canvas>
  <div id="status-text">Click to activate</div>
  <div id="transcript-text"></div>
  <div id="response-text"></div>
  <button id="settings-btn">Settings</button>
  <div id="settings-panel" class="hidden">
    <!-- settings.ts가 동적 생성 -->
  </div>
  <script type="module" src="/src/main.ts"></script>
</body>
</html>
```

### style.css 핵심 규칙

```css
/* 전체 다크 배경, 중앙 캔버스 */
body { background: #000; color: #fff; font-family: monospace; }
#orb-canvas { position: fixed; top: 0; left: 0; width: 100%; height: 100%; }
#status-text { position: fixed; bottom: 80px; width: 100%; text-align: center;
               color: #888; font-size: 14px; letter-spacing: 2px; }
#transcript-text { position: fixed; bottom: 120px; ... color: #4af; }
#response-text { position: fixed; bottom: 140px; ... color: #fff; }
#settings-btn { position: fixed; top: 20px; right: 20px; ... }
```

### ws.ts

```typescript
export class JarvisWS {
  private ws: WebSocket | null = null;
  private sessionId: string;
  private reconnectDelay = 1000;

  constructor(private url: string, private handlers: WSHandlers) {
    this.sessionId = crypto.randomUUID();
  }

  connect(): void  // WebSocket 연결 + 자동 재연결
  disconnect(): void
  send(msg: object): void
  sendSpeech(text: string): void  // {type:"speech", text, session_id}
  sendInterrupt(): void
}

interface WSHandlers {
  onStatus(state: string): void;
  onTranscript(text: string, final: boolean): void;
  onResponse(text: string, audio: string): void;  // audio: base64
  onAction(name: string, result: string): void;
  onError(msg: string): void;
}
```

### voice.ts

```typescript
export class VoiceManager {
  private recognition: SpeechRecognition;
  private audioQueue: AudioBuffer[] = [];
  private isPlaying = false;
  private audioCtx: AudioContext;
  private analyser: AnalyserNode;  // orb 연결용

  constructor(private onSpeech: (text: string, final: boolean) => void) {}

  startListening(): void   // recognition.start()
  stopListening(): void
  async playAudio(base64mp3: string): Promise<void>  // 큐에 추가 후 순차 재생
  stopAudio(): void        // 현재 재생 중단, 큐 비움
  getAnalyser(): AnalyserNode  // orb.ts에 전달
}
```

### orb.ts

```typescript
export class Orb {
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
  private particles: THREE.Points;
  private analyser: AnalyserNode | null = null;

  constructor(canvas: HTMLCanvasElement) {}

  setAnalyser(analyser: AnalyserNode): void
  setState(state: 'idle' | 'listening' | 'thinking' | 'speaking'): void
  // idle: 느린 파란 펄스
  // listening: 밝은 파란색, 마이크 입력에 반응
  // thinking: 노란색, 회전 증가
  // speaking: 초록색, TTS 오디오 진폭에 반응

  start(): void  // requestAnimationFrame 루프 시작
  stop(): void
}

// 파티클 구현:
// - BufferGeometry, 1500개 파티클
// - 구면 좌표계 배치 (랜덤 theta, phi)
// - animate()에서 AnalyserNode.getByteFrequencyData() 읽어서
//   각 파티클 반경 = BASE_RADIUS + amplitude * 0.5
// - 상태별 색상: idle=#334, listening=#04f, thinking=#fa0, speaking=#0f4
```

### main.ts (상태 머신)

```typescript
type State = 'idle' | 'listening' | 'thinking' | 'speaking';

// 초기화
const orb = new Orb(canvas);
const voice = new VoiceManager(onSpeech);
const ws = new JarvisWS('wss://localhost:8340/ws/voice', handlers);

orb.setAnalyser(voice.getAnalyser());
orb.start();
ws.connect();

// 상태 전이
// idle → click → listening (voice.startListening)
// listening → speech final → thinking (ws.sendSpeech, voice.stopListening)
// server status:thinking → UI thinking 표시
// server response 수신 → speaking (voice.playAudio)
// 재생 완료 → idle

// 클릭으로 토글: listening ↔ idle
canvas.addEventListener('click', () => { ... });
```

### settings.ts

```typescript
export class Settings {
  // 설정 패널 동적 생성 및 관리
  // 항목: user_name, voice_id(ElevenLabs), volume
  // 변경 시 ws.send({type:"settings_update", key, value})
  // localStorage에도 저장

  render(container: HTMLElement): void
  load(): Record<string, string>
  save(key: string, value: string): void
}
```

---

## 8. 설정 파일들

### requirements.txt

```
google-generativeai>=0.8.0,<1.0
httpx>=0.27.0,<1.0
fastapi>=0.115.0,<1.0
uvicorn[standard]>=0.32.0,<1.0
pydantic>=2.0.0,<3.0
websockets>=13.0,<16.0
playwright>=1.40.0,<2.0
pyyaml>=6.0,<7.0
sounddevice>=0.4.6,<1.0
numpy>=1.26.0,<3.0
```

### frontend/package.json

```json
{
  "name": "jarvis-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "devDependencies": {
    "typescript": "^5.7.0",
    "vite": "^6.0.0"
  },
  "dependencies": {
    "@types/three": "^0.183.1",
    "three": "^0.183.2"
  }
}
```

### frontend/tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"]
}
```

### frontend/vite.config.ts

```typescript
import { defineConfig } from "vite";

export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      "/ws": {
        target: "https://localhost:8340",
        ws: true,
        secure: false,
      },
      "/api": {
        target: "https://localhost:8340",
        secure: false,
      },
    },
  },
  build: { outDir: "dist" },
});
```

### .gitignore

```
.env
node_modules/
.venv/
__pycache__/
*.pyc
*.db
*.db-shm
*.db-wal
data/*.jsonl
data/active_session.json
data/.jarvis_output.txt
*.pem
dist/
.vite/
frontend/.vite/
.DS_Store
```

---

## 9. 실행 방법

```bash
# 1. 가상환경 생성
python3 -m venv .venv && source .venv/bin/activate

# 2. 패키지 설치
pip install -r requirements.txt
playwright install chromium

# 3. 환경변수 설정
cp .env.example .env
# .env 파일에 API 키 입력

# 4. 프론트엔드 설치
cd frontend && npm install && cd ..

# 5. SSL 인증서 생성 (최초 1회)
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem \
  -days 365 -nodes -subj '/CN=localhost'

# 6. 백엔드 실행 (터미널 1)
source .venv/bin/activate && python server.py

# 7. 프론트엔드 실행 (터미널 2)
cd frontend && npm run dev

# 8. 브라우저 열기
open http://localhost:5173
# 캔버스 클릭 → 말하기
```

---

## 10. 구현 순서 (다음 세션에서 이 순서대로)

1. `.env.example`, `.gitignore`, `requirements.txt` 생성
2. `memory.py` 구현 및 단위 테스트
3. `actions.py` 구현
4. `browser.py` 구현
5. `work_mode.py` 구현
6. `planner.py` 구현
7. `server.py` 구현 (REST API → WebSocket 순)
8. 설정 파일 생성 (`package.json`, `tsconfig.json`, `vite.config.ts`)
9. `frontend/src/style.css`
10. `frontend/src/ws.ts`
11. `frontend/src/voice.ts`
12. `frontend/src/orb.ts`
13. `frontend/src/settings.ts`
14. `frontend/src/main.ts`
15. `frontend/index.html`
16. 의존성 설치, SSL 인증서, 통합 테스트

---

## 11. 알려진 제약 / 주의사항

- macOS 전용 (AppleScript, `say` 명령어)
- Web Speech API는 HTTPS 또는 localhost에서만 동작
- ElevenLabs 무료 티어: 월 10,000자. 초과 시 macOS `say` 자동 폴백
- Chrome 권장 (Firefox는 Web Speech API 지원 불안정)
- `work_mode.py`는 로컬에 `claude` CLI가 설치되어 있어야 함
- SSL 인증서 자체 서명이므로 브라우저에서 최초 접속 시 경고 → 고급 → 계속 클릭 필요
