export interface WSHandlers {
  onStatus(state: string): void;
  onTranscript(text: string, final: boolean): void;
  onResponse(text: string, audio: string): void;
  onGreeting(text: string, audio: string): void;
  onAction(name: string, result: string): void;
  onError(message: string): void;
  onWake?(): void;
  onShutdown?(): void;
  onConnected?(): void;
}

export class JarvisWS {
  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 16000;
  private shouldReconnect = true;
  readonly sessionId: string;

  constructor(
    private readonly url: string,
    private readonly handlers: WSHandlers
  ) {
    this.sessionId = crypto.randomUUID();
  }

  connect(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return;

    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectDelay = 1000;
      this._startPing();
      this.handlers.onConnected?.();
    };

    this.ws.onmessage = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(ev.data as string) as Record<string, unknown>;
        const type = msg.type as string;

        switch (type) {
          case "status":
            this.handlers.onStatus(msg.state as string);
            break;
          case "transcript":
            this.handlers.onTranscript(
              msg.text as string,
              Boolean(msg.final)
            );
            break;
          case "response":
            this.handlers.onResponse(
              msg.text as string,
              msg.audio as string
            );
            break;
          case "greeting":
            this.handlers.onGreeting(
              msg.text as string,
              msg.audio as string
            );
            break;
          case "action":
            this.handlers.onAction(
              msg.name as string,
              msg.result as string
            );
            break;
          case "error":
            this.handlers.onError(msg.message as string);
            break;
          case "wake":
            this.handlers.onWake?.();
            break;
          case "shutdown":
            this.handlers.onShutdown?.();
            break;
          case "pong":
            break;
        }
      } catch {
        // ignore parse errors
      }
    };

    this.ws.onclose = () => {
      this._clearPing();
      if (this.shouldReconnect) this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  disconnect(): void {
    this.shouldReconnect = false;
    this._clearPing();
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }

  send(obj: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
    }
  }

  sendSpeech(text: string): void {
    this.send({ type: "speech", text, session_id: this.sessionId });
  }

  sendInterrupt(): void {
    this.send({ type: "interrupt" });
  }

  sendSettingUpdate(key: string, value: string): void {
    this.send({ type: "settings_update", key, value });
  }

  // ── Internal ──────────────────────────────────────────────────────────────

  private _pingTimer: ReturnType<typeof setInterval> | null = null;

  private _startPing(): void {
    this._pingTimer = setInterval(() => {
      this.send({ type: "ping" });
    }, 20000);
  }

  private _clearPing(): void {
    if (this._pingTimer) {
      clearInterval(this._pingTimer);
      this._pingTimer = null;
    }
  }

  private _scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectDelay = Math.min(
        this.reconnectDelay * 2,
        this.maxReconnectDelay
      );
      this.connect();
    }, this.reconnectDelay);
  }
}
