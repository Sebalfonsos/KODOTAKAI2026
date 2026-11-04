import { peticion } from "./http";

// Voz (docs/frontend.md §4.1): el audio se transcribe y entra al mismo chat; la respuesta se sintetiza frase a frase.

export type Voz = "female" | "male";

export async function transcribir(audio: Blob): Promise<string> {
  const cuerpo = new FormData();
  const ext = audio.type.includes("ogg") ? "ogg" : audio.type.includes("mp4") ? "mp4" : "webm";
  cuerpo.set("audio", audio, `audio.${ext}`);
  // `json()` reescribe el cuerpo: el multipart va por `peticion`.
  const r = await peticion("/api/v1/voz/transcribir", { method: "POST", body: cuerpo });
  return ((await r.json()) as { texto: string }).texto.trim();
}

async function sintetizar(texto: string, voz: Voz, signal: AbortSignal): Promise<Blob> {
  const r = await peticion("/api/v1/voz/sintetizar", {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ texto, voz }),
  });
  return r.blob();
}

/** ponytail: corte por puntuación, sin cuidar abreviaturas; el resumen ya llega en frases cortas. */
export const frases = (t: string) => (t.match(/[^.!?…]+[.!?…]*/g) ?? []).map((f) => f.trim()).filter(Boolean);

function reproducir(blob: Blob, signal: AbortSignal): Promise<void> {
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  return new Promise<void>((ok, falla) => {
    const fin = () => {
      URL.revokeObjectURL(url);
      ok();
    };
    signal.addEventListener("abort", () => {
      audio.pause();
      fin();
    });
    audio.onended = fin;
    audio.onerror = () => falla(new Error("No se pudo reproducir el audio."));
    audio.play().catch(falla);
  });
}

/**
 * Lee el texto en voz alta. El backend genera una frase a la vez: se pide la siguiente mientras suena la actual,
 * nunca dos en paralelo. Abortar la señal corta el audio y las peticiones pendientes.
 */
export async function hablar(texto: string, voz: Voz, signal: AbortSignal): Promise<void> {
  const lista = frases(texto);
  let siguiente = lista.length ? sintetizar(lista[0], voz, signal) : null;
  for (let i = 0; siguiente && !signal.aborted; i++) {
    const blob = await siguiente;
    siguiente = i + 1 < lista.length ? sintetizar(lista[i + 1], voz, signal) : null;
    // Evita un rechazo sin manejar si se aborta antes de esperarla.
    siguiente?.catch(() => undefined);
    await reproducir(blob, signal);
  }
}

export type FaseDetector = "esperando" | "hablando" | "fin" | "sin_voz";

/**
 * Detector de voz por energía (RMS), sin dependencias. Calibra el ruido de fondo al inicio, marca voz cuando la
 * energía supera ese piso y termina tras un silencio sostenido. Evita mandar silencio al STT (inventa frases).
 * ponytail: umbral por energía, no un VAD entrenado; con ruido fuerte y constante (calle, música) puede no cortar,
 * y entonces corta el tope de duración o el segundo toque.
 */
export class DetectorVoz {
  private ruido = 0;
  private muestrasRuido = 0;
  private vozMs = 0;
  private silencioMs = 0;
  private totalMs = 0;
  fase: FaseDetector = "esperando";

  constructor(
    private readonly calibrarMs = 250,
    private readonly silencioFinMs = 1300,
    private readonly sinVozMs = 8000,
    private readonly minVozMs = 250,
  ) {}

  /** `rms` entre 0 y 1; `ms` es el tiempo desde la muestra anterior. */
  muestra(rms: number, ms: number): FaseDetector {
    this.totalMs += ms;
    if (this.totalMs <= this.calibrarMs) {
      this.ruido = (this.ruido * this.muestrasRuido + rms) / ++this.muestrasRuido;
      return this.fase;
    }
    // Tope: si el usuario ya hablaba durante la calibración, su voz no puede quedar como "ruido".
    const umbral = Math.min(0.04, Math.max(0.012, this.ruido * 2.5));
    if (rms > umbral) {
      this.vozMs += ms;
      this.silencioMs = 0;
      if (this.vozMs >= this.minVozMs) this.fase = "hablando";
    } else if (this.fase === "hablando") {
      this.silencioMs += ms;
      if (this.silencioMs >= this.silencioFinMs) this.fase = "fin";
    } else if (this.totalMs >= this.sinVozMs) {
      this.fase = "sin_voz";
    }
    return this.fase;
  }

  get huboVoz() {
    return this.vozMs >= this.minVozMs;
  }
}
