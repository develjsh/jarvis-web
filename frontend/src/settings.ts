import type { JarvisWS } from "./ws.ts";

const KEYS = ["user_name", "voice_id", "volume"] as const;
type SettingKey = (typeof KEYS)[number];

const LABELS: Record<SettingKey, string> = {
  user_name: "Your Name",
  voice_id:  "ElevenLabs Voice ID",
  volume:    "Volume",
};

export class Settings {
  private data: Record<string, string> = {};

  constructor(private readonly ws: JarvisWS) {
    this.data = this._load();
  }

  render(container: HTMLElement): void {
    container.innerHTML = "<h3>Settings</h3>";

    for (const key of KEYS) {
      const row = document.createElement("div");
      row.className = "setting-row";

      const label = document.createElement("label");
      label.textContent = LABELS[key];
      row.appendChild(label);

      if (key === "volume") {
        const input = document.createElement("input");
        input.type = "range";
        input.min = "0";
        input.max = "100";
        input.value = this.data[key] ?? "80";
        input.id = `setting-${key}`;
        row.appendChild(input);
      } else {
        const input = document.createElement("input");
        input.type = "text";
        input.value = this.data[key] ?? "";
        input.placeholder =
          key === "voice_id" ? "JBFqnCBsd6RMkjVDRZzb" : "";
        input.id = `setting-${key}`;
        row.appendChild(input);
      }

      container.appendChild(row);
    }

    const btn = document.createElement("button");
    btn.className = "settings-save";
    btn.textContent = "Save";
    btn.addEventListener("click", () => this._save(container));
    container.appendChild(btn);
  }

  private _save(container: HTMLElement): void {
    for (const key of KEYS) {
      const el = container.querySelector<HTMLInputElement>(`#setting-${key}`);
      if (!el) continue;
      const value = el.value.trim();
      this.data[key] = value;
      this.ws.sendSettingUpdate(key, value);
    }
    localStorage.setItem("jarvis_settings", JSON.stringify(this.data));
  }

  private _load(): Record<string, string> {
    try {
      return JSON.parse(localStorage.getItem("jarvis_settings") ?? "{}");
    } catch {
      return {};
    }
  }

  get(key: SettingKey): string {
    return this.data[key] ?? "";
  }
}
