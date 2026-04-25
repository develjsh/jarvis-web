import * as THREE from "three";

export type OrbState = "idle" | "listening" | "thinking" | "speaking";

const STATE_COLORS: Record<OrbState, THREE.Color> = {
  idle:      new THREE.Color(0x112244),
  listening: new THREE.Color(0x0044ff),
  thinking:  new THREE.Color(0xffaa00),
  speaking:  new THREE.Color(0x00ff66),
};

const PARTICLE_COUNT = 1500;
const BASE_RADIUS = 1.8;

export class Orb {
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
  private particles: THREE.Points;
  private geometry: THREE.BufferGeometry;
  private basePositions: Float32Array;

  private analyser: AnalyserNode | null = null;
  private freqData: Uint8Array | null = null;

  private state: OrbState = "idle";
  private targetColor = STATE_COLORS.idle.clone();
  private currentColor = STATE_COLORS.idle.clone();

  private clock = new THREE.Clock();
  private rafId: number | null = null;

  constructor(private readonly canvas: HTMLCanvasElement) {
    this.scene = new THREE.Scene();

    this.camera = new THREE.PerspectiveCamera(
      60,
      canvas.clientWidth / canvas.clientHeight,
      0.1,
      100
    );
    this.camera.position.z = 5;

    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);

    // Build particle geometry
    const positions = new Float32Array(PARTICLE_COUNT * 3);
    this.basePositions = new Float32Array(PARTICLE_COUNT * 3);

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const x = BASE_RADIUS * Math.sin(phi) * Math.cos(theta);
      const y = BASE_RADIUS * Math.sin(phi) * Math.sin(theta);
      const z = BASE_RADIUS * Math.cos(phi);
      positions[i * 3]     = x;
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = z;
      this.basePositions[i * 3]     = x;
      this.basePositions[i * 3 + 1] = y;
      this.basePositions[i * 3 + 2] = z;
    }

    this.geometry = new THREE.BufferGeometry();
    this.geometry.setAttribute(
      "position",
      new THREE.BufferAttribute(positions, 3)
    );

    const material = new THREE.PointsMaterial({
      size: 0.025,
      color: this.currentColor,
      transparent: true,
      opacity: 0.85,
      sizeAttenuation: true,
    });

    this.particles = new THREE.Points(this.geometry, material);
    this.scene.add(this.particles);

    // Resize observer
    const ro = new ResizeObserver(() => this._onResize());
    ro.observe(canvas);
  }

  setAnalyser(analyser: AnalyserNode): void {
    this.analyser = analyser;
    this.freqData = new Uint8Array(analyser.frequencyBinCount);
  }

  setState(state: OrbState): void {
    this.state = state;
    this.targetColor = STATE_COLORS[state].clone();
  }

  start(): void {
    this.clock.start();
    this._animate();
  }

  stop(): void {
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
  }

  private _animate(): void {
    this.rafId = requestAnimationFrame(() => this._animate());

    const t = this.clock.getElapsedTime();
    const mat = this.particles.material as THREE.PointsMaterial;

    // Lerp color
    this.currentColor.lerp(this.targetColor, 0.05);
    mat.color.copy(this.currentColor);

    // Get audio amplitude
    let amplitude = 0;
    if (this.analyser && this.freqData) {
      this.analyser.getByteFrequencyData(this.freqData);
      let sum = 0;
      for (let i = 0; i < this.freqData.length; i++) {
        sum += this.freqData[i];
      }
      amplitude = sum / (this.freqData.length * 255);
    }

    // Rotate
    const rotSpeed =
      this.state === "thinking" ? 0.6 : this.state === "speaking" ? 0.3 : 0.1;
    this.particles.rotation.y += rotSpeed * 0.01;
    this.particles.rotation.x += rotSpeed * 0.005;

    // Deform positions
    const pos = this.geometry.attributes.position as THREE.BufferAttribute;
    const arr = pos.array as Float32Array;

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const bx = this.basePositions[i * 3];
      const by = this.basePositions[i * 3 + 1];
      const bz = this.basePositions[i * 3 + 2];

      // Pulse
      const pulse =
        1 +
        Math.sin(t * 1.5 + i * 0.01) * 0.04 +
        amplitude * 0.6;

      arr[i * 3]     = bx * pulse;
      arr[i * 3 + 1] = by * pulse;
      arr[i * 3 + 2] = bz * pulse;
    }
    pos.needsUpdate = true;

    // Opacity pulse for idle
    mat.opacity =
      this.state === "idle"
        ? 0.4 + Math.sin(t * 1.2) * 0.15
        : 0.85;

    this.renderer.render(this.scene, this.camera);
  }

  private _onResize(): void {
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
  }
}
