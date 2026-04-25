import "./style.css";
import { Orb, type OrbState } from "./orb.ts";
import { VoiceManager } from "./voice.ts";
import { JarvisWS } from "./ws.ts";
import { Settings } from "./settings.ts";


// ── DOM refs ──────────────────────────────────────────────────────────────────

const canvas       = document.getElementById("orb-canvas")       as HTMLCanvasElement;
const statusEl     = document.getElementById("status-text")       as HTMLDivElement;
const transcriptEl = document.getElementById("transcript-text")   as HTMLDivElement;
const responseEl   = document.getElementById("response-text")     as HTMLDivElement;
const actionEl     = document.getElementById("action-text")       as HTMLDivElement;
const settingsBtn  = document.getElementById("settings-btn")      as HTMLButtonElement;
const settingsPanel= document.getElementById("settings-panel")    as HTMLDivElement;

// ── State ─────────────────────────────────────────────────────────────────────

type AppState = "idle" | "listening" | "thinking" | "speaking";

let appState: AppState = "idle";
let actionTimer: ReturnType<typeof setTimeout> | null = null;
let thinkingTimer: ReturnType<typeof setTimeout> | null = null;

const THINKING_TIMEOUT_MS = 60000;

function clearThinkingTimer(): void {
  if (thinkingTimer) {
    clearTimeout(thinkingTimer);
    thinkingTimer = null;
  }
}

function setState(next: AppState): void {
  appState = next;
  orb.setState(next as OrbState);
  statusEl.className = next === "idle" ? "" : next;
  clearThinkingTimer();

  switch (next) {
    case "idle":
      statusEl.textContent = "Listening...";
      break;
    case "listening":
      statusEl.textContent = "Listening";
      transcriptEl.textContent = "";
      break;
    case "thinking":
      statusEl.textContent = "Thinking...";
      thinkingTimer = setTimeout(() => {
        statusEl.textContent = "No response — try again";
        statusEl.className = "error";
        ws.sendInterrupt();
        setTimeout(() => {
          if (appState === "thinking") {
            setState("idle");
            startListening();
          }
        }, 2000);
      }, THINKING_TIMEOUT_MS);
      break;
    case "speaking":
      statusEl.textContent = "Speaking";
      break;
  }
}

function showAction(name: string, result: string): void {
  const short = result.length > 80 ? result.slice(0, 77) + "…" : result;
  actionEl.textContent = `${name}: ${short}`;
  actionEl.classList.add("visible");

  if (actionTimer) clearTimeout(actionTimer);
  actionTimer = setTimeout(() => {
    actionEl.classList.remove("visible");
  }, 5000);
}

// ── Core components ───────────────────────────────────────────────────────────

const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
const wsUrl = `${wsProto}//${window.location.host}/ws/voice`;

const ws = new JarvisWS(wsUrl, {
  onStatus(state: string) {
    if (state === "thinking") {
      setState("thinking");
      voice.stopListening();
    } else if (state === "speaking") {
      setState("speaking");
    } else if (state === "idle") {
      setState("idle");
      setTimeout(() => {
        if (appState === "idle") startListening();
      }, 300);
    }
  },

  onTranscript(text: string, final: boolean) {
    if (final) voice.stopListening();
  },

  onGreeting(_text: string, _audio: string) {
    // 서버가 afplay로 직접 재생 — 프론트엔드는 상태만 처리
  },

  onResponse(_text: string, _audio: string) {
    // 서버가 afplay로 직접 재생 — 프론트엔드는 상태만 처리
  },

  onAction(name: string, result: string) {
    showAction(name, result);
  },

  onError(message: string) {
    console.error("JARVIS error:", message);
    setState("idle");
  },

  onWake() {
    if (appState === "idle") {
      startListening();
    }
  },

  onConnected() {
    // 서버가 greeting 재생 후 idle 상태를 전송하면 자동으로 listening 시작
  },

  onShutdown() {
    statusEl.textContent = "Shutting down...";
    voice.stopAudio();
    voice.stopListening();
    ws.disconnect();
    setTimeout(() => window.close(), 2000);
  },
});

const voice = new VoiceManager((text, final) => {
  transcriptEl.textContent = text;
  if (final) {
    ws.sendSpeech(text);
    setState("thinking");
    voice.stopListening();
  }
});

voice.setOnPlaybackEnd(() => {
  // 브라우저 오디오 재생 종료 시 (현재 미사용, 서버 afplay로 대체)
});

const orb = new Orb(canvas);
orb.setAnalyser(voice.getAnalyser());
orb.start();

const settings = new Settings(ws);

// ── Interactions ──────────────────────────────────────────────────────────────

function startListening(): void {
  voice.resumeContext();
  setState("listening");
  voice.startListening();
}

function stopListening(): void {
  voice.stopListening();
  setState("idle");
}

canvas.addEventListener("click", () => {
  if (appState === "idle") {
    startListening();
  } else if (appState === "listening") {
    stopListening();
  } else if (appState === "speaking") {
    voice.stopAudio();
    ws.sendInterrupt();
    setState("idle");
  }
});

// Settings panel toggle
settingsBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  settingsPanel.classList.toggle("hidden");
  if (!settingsPanel.classList.contains("hidden")) {
    settings.render(settingsPanel);
  }
});

document.addEventListener("click", (e) => {
  if (!settingsPanel.contains(e.target as Node) && e.target !== settingsBtn) {
    settingsPanel.classList.add("hidden");
  }
});

// ── Init ──────────────────────────────────────────────────────────────────────

ws.connect();
setState("idle");

window.addEventListener("beforeunload", () => {
  ws.send({ type: "bye" });
  ws.disconnect();
});
