import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorApi } from "../services/http";
import { DetectorVoz, hablar, transcribir, type Voz } from "../services/voz";

const CLAVE_LEER = "translogix.voz.leer";
const MIN_MS = 600;
const MAX_MS = 30_000;
const LIBERAR_MS = 20_000;

type Motivo = "manual" | "fin_voz" | "sin_voz" | "tope";

function leerPreferencia(): boolean {
  try {
    return localStorage.getItem(CLAVE_LEER) !== "0";
  } catch {
    return true;
  }
}

/** Micrófono → texto, y respuestas → voz. Si la voz falla, el chat sigue en texto y se avisa una vez. */
export function useVoz(voz: Voz = "female") {
  const [leer, setLeerEstado] = useState(leerPreferencia);
  const [hablando, setHablando] = useState(false);
  const [grabando, setGrabando] = useState(false);
  const [transcribiendo, setTranscribiendo] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const lectura = useRef<AbortController | null>(null);
  const grabadora = useRef<MediaRecorder | null>(null);
  const flujo = useRef<MediaStream | null>(null);
  const relojLiberar = useRef<number>(undefined);
  const motivoFin = useRef<Motivo>("manual");
  const preparando = useRef(false);
  const [preparandoEstado, setPreparandoEstado] = useState(false);
  const nivel = useRef<HTMLButtonElement>(null);

  const callar = useCallback(() => {
    lectura.current?.abort();
    lectura.current = null;
    setHablando(false);
  }, []);

  const decir = useCallback(
    async (texto: string) => {
      callar();
      if (!texto) return;
      const control = new AbortController();
      lectura.current = control;
      setHablando(true);
      try {
        await hablar(texto, voz, control.signal);
      } catch (e) {
        // Sin un clic previo el navegador bloquea el audio: no es una falla de la voz, solo se omite la lectura.
        const bloqueado = e instanceof DOMException && e.name === "NotAllowedError";
        if (!control.signal.aborted && !bloqueado) {
          setAviso(
            e instanceof ErrorApi && e.problema.codigo === "VOZ_NO_DISPONIBLE"
              ? "La voz no está disponible ahora: te respondo solo en texto."
              : "No pude leer la respuesta en voz alta: te respondo solo en texto.",
          );
        }
      } finally {
        if (lectura.current === control) {
          lectura.current = null;
          setHablando(false);
        }
      }
    },
    [voz, callar],
  );

  const setLeer = useCallback(
    (v: boolean) => {
      setLeerEstado(v);
      if (!v) callar();
      try {
        localStorage.setItem(CLAVE_LEER, v ? "1" : "0");
      } catch {
        // La preferencia solo dura esta visita.
      }
    },
    [callar],
  );

  const liberarFlujo = useCallback(() => {
    window.clearTimeout(relojLiberar.current);
    flujo.current?.getTracks().forEach((t) => t.stop());
    flujo.current = null;
  }, []);

  /**
   * El micrófono se reutiliza unos segundos entre grabaciones: abrirlo cada vez tarda y se comía las primeras
   * palabras. Se libera solo tras un rato sin usarse (el navegador deja de mostrar el indicador).
   */
  const obtenerFlujo = useCallback(async () => {
    window.clearTimeout(relojLiberar.current);
    if (flujo.current?.getAudioTracks().some((t) => t.readyState === "live")) return flujo.current;
    flujo.current = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });
    return flujo.current;
  }, []);

  const detener = useCallback((motivo: Motivo = "manual") => {
    const g = grabadora.current;
    if (g?.state !== "recording") return;
    motivoFin.current = motivo;
    g.stop();
  }, []);

  /** Graba hasta que el usuario deja de hablar (o toca de nuevo), transcribe y entrega el texto. */
  const iniciar = useCallback(
    async (alTexto: (texto: string) => void) => {
      if (grabadora.current || preparando.current) return;
      callar(); // si RUTI está hablando y el usuario habla, se interrumpe
      setAviso(null);
      preparando.current = true;
      setPreparandoEstado(true);
      let audio: MediaStream;
      try {
        audio = await obtenerFlujo();
      } catch {
        setAviso("No tengo acceso al micrófono. Revisa el permiso del navegador.");
        return;
      } finally {
        preparando.current = false;
        setPreparandoEstado(false);
      }

      const trozos: Blob[] = [];
      const g = new MediaRecorder(audio);
      const detector = new DetectorVoz();
      motivoFin.current = "manual";

      // Nivel de entrada: alimenta el detector y el anillo del botón.
      const ctx = new AudioContext();
      const analizador = ctx.createAnalyser();
      analizador.fftSize = 1024;
      ctx.createMediaStreamSource(audio).connect(analizador);
      const buffer = new Float32Array(analizador.fftSize);
      let anterior = performance.now();
      const medir = window.setInterval(() => {
        analizador.getFloatTimeDomainData(buffer);
        const rms = Math.sqrt(buffer.reduce((a, v) => a + v * v, 0) / buffer.length);
        const ahora = performance.now();
        const fase = detector.muestra(rms, ahora - anterior);
        anterior = ahora;
        nivel.current?.style.setProperty("--nivel", Math.min(1, rms * 8).toFixed(2));
        if (fase === "fin") detener("fin_voz");
        else if (fase === "sin_voz") detener("sin_voz");
      }, 50);
      const tope = window.setTimeout(() => detener("tope"), MAX_MS);
      let inicio = 0;

      g.onstart = () => {
        inicio = performance.now();
        setGrabando(true);
      };
      g.ondataavailable = (e) => e.data.size && trozos.push(e.data);
      g.onstop = async () => {
        window.clearInterval(medir);
        window.clearTimeout(tope);
        void ctx.close();
        nivel.current?.style.setProperty("--nivel", "0");
        grabadora.current = null;
        setGrabando(false);
        relojLiberar.current = window.setTimeout(liberarFlujo, LIBERAR_MS);

        const motivo = motivoFin.current;
        // Sin voz detectada no se transcribe: con silencio o ruido el STT inventa frases.
        // Si el usuario lo detuvo y grabó algo razonable, se respeta su intención aunque el detector dudara.
        const corto = performance.now() - inicio < MIN_MS;
        if (motivo === "sin_voz" || (!detector.huboVoz && (corto || motivo !== "manual"))) {
          setAviso("No te escuché. Toca el micrófono y habla cerca de él.");
          return;
        }
        setTranscribiendo(true);
        try {
          const texto = await transcribir(new Blob(trozos, { type: g.mimeType }));
          if (texto) alTexto(texto);
          else setAviso("No entendí el audio. ¿Lo intentamos de nuevo?");
        } catch (e) {
          setAviso(
            e instanceof ErrorApi ? (e.problema.detail ?? e.problema.title) : "No pude transcribir el audio. Revisa tu conexión.",
          );
        } finally {
          setTranscribiendo(false);
        }
      };
      grabadora.current = g;
      g.start();
    },
    [callar, obtenerFlujo, detener, liberarFlujo],
  );

  useEffect(
    () => () => {
      lectura.current?.abort();
      detener();
      liberarFlujo();
    },
    [detener, liberarFlujo],
  );

  const microfonoDisponible = typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && "MediaRecorder" in window;

  return {
    leer,
    setLeer,
    hablando,
    decir,
    callar,
    grabando,
    preparando: preparandoEstado,
    transcribiendo,
    iniciar,
    detener,
    /** Elemento que recibe `--nivel` (0–1) mientras se graba. */
    nivel,
    microfonoDisponible,
    aviso,
    cerrarAviso: () => setAviso(null),
  };
}
