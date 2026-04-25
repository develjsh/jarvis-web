type SpeechCallback = (text: string, final: boolean) => void;

const LANGS = ["ko-KR", "en-US"] as const;

export class VoiceManager {
  private _SR: typeof SpeechRecognition | null = null;
  private _rec: SpeechRecognition | null = null;
  private _langIdx = 0;
  private _running = false;
  private _shouldListen = false;
  private _finalPending = false;
  private audioCtx: AudioContext;
  private analyser: AnalyserNode;
  private sourceNode: AudioBufferSourceNode | null = null;
  private isPlaying = false;
  private queue: AudioBuffer[] = [];
  private pendingQueue: AudioBuffer[] = [];
  private onPlaybackEnd: (() => void) | null = null;

  constructor(private readonly onSpeech: SpeechCallback) {
    this.audioCtx = new AudioContext();
    this.analyser = this.audioCtx.createAnalyser();
    this.analyser.fftSize = 256;
    this.analyser.connect(this.audioCtx.destination);

    this._SR =
      (window as unknown as { SpeechRecognition: typeof SpeechRecognition })
        .SpeechRecognition ??
      (window as unknown as { webkitSpeechRecognition: typeof SpeechRecognition })
        .webkitSpeechRecognition ??
      null;
  }

  // ── Speech recognition ────────────────────────────────────────────────────

  private _buildRec(lang: string): SpeechRecognition {
    const r = new this._SR!();
    r.continuous = true;
    r.interimResults = true;
    r.lang = lang;
    r.maxAlternatives = 1;

    r.onresult = (ev: SpeechRecognitionEvent) => {
      let interim = "";
      let finalText = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const t = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) finalText += t;
        else interim += t;
      }
      if (finalText && !this._finalPending) {
        this._finalPending = true;
        this._langIdx = this._detectLangIdx(finalText);
        this.onSpeech(finalText.trim(), true);
      } else if (interim && !this._finalPending) {
        this.onSpeech(interim.trim(), false);
      }
    };

    r.onerror = (ev: SpeechRecognitionErrorEvent) => {
      if (ev.error === "no-speech" || ev.error === "aborted") return;
      console.warn(`[${lang}] error:`, ev.error);
    };

    r.onend = () => {
      this._running = false;
      if (this._shouldListen) {
        setTimeout(() => {
          if (this._shouldListen && !this._running) {
            this._rec = this._buildRec(LANGS[this._langIdx]);
            try { this._rec.start(); this._running = true; } catch {}
          }
        }, 200);
      }
    };

    return r;
  }

  private _detectLangIdx(text: string): number {
    const korean = (text.match(/[가-힯㄰-㆏]/g) ?? []).length;
    return korean > 0 ? 0 : 1;
  }

  startListening(): void {
    this._shouldListen = true;
    this._finalPending = false;
    if (this.audioCtx.state === "suspended") void this.audioCtx.resume();
    if (!this._running && this._SR) {
      this._rec = this._buildRec(LANGS[this._langIdx]);
      try { this._rec.start(); this._running = true; } catch {}
    }
  }

  stopListening(): void {
    this._shouldListen = false;
    this._running = false;
    try { this._rec?.stop(); } catch {}
    this._rec = null;
  }

  // ── Audio playback ────────────────────────────────────────────────────────

  setOnPlaybackEnd(cb: () => void): void {
    this.onPlaybackEnd = cb;
  }

  async playAudio(base64: string, pending = false): Promise<void> {
    if (!base64) return;

    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }

    try {
      const buffer = await this.audioCtx.decodeAudioData(bytes.buffer);
      if (pending || this.audioCtx.state === "suspended") {
        this.pendingQueue.push(buffer);
      } else {
        this.queue.push(buffer);
        if (!this.isPlaying) this._playNext();
      }
    } catch {
      // decode failed — skip
    }
  }

  private _playNext(): void {
    const buffer = this.queue.shift();
    if (!buffer) {
      this.isPlaying = false;
      this.onPlaybackEnd?.();
      return;
    }

    this.isPlaying = true;
    const src = this.audioCtx.createBufferSource();
    src.buffer = buffer;
    src.connect(this.analyser);
    this.sourceNode = src;

    src.onended = () => {
      this._playNext();
    };
    src.start();
  }

  stopAudio(): void {
    this.queue = [];
    try {
      this.sourceNode?.stop();
    } catch {
      // already stopped
    }
    this.sourceNode = null;
    this.isPlaying = false;
  }

  getAnalyser(): AnalyserNode {
    return this.analyser;
  }

  resumeContext(onPendingFlush?: () => void): void {
    if (this.audioCtx.state === "suspended") {
      void this.audioCtx.resume().then(() => {
        if (this.pendingQueue.length > 0) {
          for (const buf of this.pendingQueue) {
            this.queue.push(buf);
          }
          this.pendingQueue = [];
          onPendingFlush?.();
          if (!this.isPlaying) this._playNext();
        }
      });
    }
  }

  hasPending(): boolean {
    return this.pendingQueue.length > 0;
  }
}
