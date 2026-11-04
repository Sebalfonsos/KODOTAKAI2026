import { hablar } from "../../services/voz";
import type { FaseEscalamiento } from "../../state/chatStore";
import type { EstadoRuti } from "../../state/rutiMachine";

// Demostración de la portada: es un guion etiquetado, no una conversación. No llama al chat ni inventa cifras,
// estados de envío o veredictos (ESTRUCTURA_FRONT.md §2, principios 2 y 7). Por eso aquí sí manda el reloj.

export type FaseShow = "reposo" | "activo" | "calma" | "resumen";

export interface CasoVista {
  id: number;
  quien: string;
  iniciales: string;
  texto: string;
  fila: number;
  resuelto: boolean;
}

export interface FilaVista {
  clave: string;
  valor: string;
  lista: boolean;
}

export interface VistaShow {
  fase: FaseShow;
  estado: EstadoRuti;
  escalamiento: FaseEscalamiento | null;
  linea: string;
  final: boolean;
  hablando: boolean;
  panel: boolean;
  celebrando: boolean;
  casos: CasoVista[];
  filas: FilaVista[];
}

const FILAS = [
  { clave: "Rastreo", valor: "línea de tiempo del envío" },
  { clave: "Cotización", valor: "valor con su desglose" },
  { clave: "Dudas", valor: "respuesta con fuente citada" },
  { clave: "Reclamación", valor: "checklist de documentos" },
  { clave: "Asesor", valor: "traspaso con el historial" },
];

/** Datos de ejemplo. `TLX-000123-CO` no existe en el dataset del TMS. `fila` es la fila del panel que lo atiende. */
const MENSAJES = [
  { quien: "Marta G.", iniciales: "MG", texto: "¿Dónde está mi guía TLX-000123-CO?", fila: 0 },
  { quien: "Óscar P.", iniciales: "OP", texto: "Ya van dos llamadas y nadie me dice dónde está mi envío.", fila: 0 },
  { quien: "Ana L.", iniciales: "AL", texto: "¿Cuánto me sale enviar 3 cajas de Bogotá a Cali?", fila: 1 },
  { quien: "Julián R.", iniciales: "JR", texto: "¿Puedo enviar pintura en aerosol?", fila: 2 },
  { quien: "Sofía C.", iniciales: "SC", texto: "¿Cómo embalo una nevera?", fila: 2 },
  { quien: "Camilo T.", iniciales: "CT", texto: "¿Tienen cobertura en mi municipio?", fila: 2 },
  { quien: "Laura V.", iniciales: "LV", texto: "Mi paquete llegó dañado. ¿Qué documentos necesito?", fila: 3 },
  { quien: "Diego M.", iniciales: "DM", texto: "Quiero hablar con una persona.", fila: 4 },
];

const MENSAJE_FINAL = "Lo repetitivo, resuelto. Lo delicado, con un asesor.";

interface Base extends Omit<VistaShow, "casos" | "filas"> {
  llegados: number;
  escritas: number;
  listas: number;
}

type Evento = { t: number } & Partial<Base>;

const BASE: Base = {
  fase: "reposo",
  estado: "reposo",
  escalamiento: null,
  linea: "",
  final: false,
  hablando: false,
  panel: false,
  celebrando: false,
  llegados: 0,
  escritas: 0,
  listas: 0,
};

/** Cada evento cambia solo lo que nombra. Los mensajes llegan cada vez más rápido: es la tensión del show. */
export const LINEA_TIEMPO: Evento[] = [
  { t: 0, fase: "activo", estado: "escuchando", linea: "A ver, ¿qué tenemos hoy?" },
  ...[200, 900, 1500, 2000, 2450, 2850, 3200, 3500].map((t, i) => ({ t, llegados: i + 1 })),
  { t: 4500, estado: "pensando", linea: "Calma, ya los vi. Uno por uno." },
  { t: 5500, estado: "reposo", hablando: true, panel: true },
  { t: 5700, escritas: 1 },
  { t: 6350, listas: 1 },
  { t: 6500, escritas: 2 },
  { t: 7150, listas: 2 },
  { t: 7300, escritas: 3 },
  { t: 7950, listas: 3 },
  { t: 8100, escritas: 4 },
  { t: 8750, listas: 4 },
  {
    t: 9500,
    estado: "escalamiento",
    escalamiento: "transfiriendo",
    hablando: false,
    linea: "Esto amerita una persona. En una conversación real, te paso con un asesor.",
  },
  { t: 10000, escritas: 5 },
  { t: 10900, listas: 5 },
  { t: 11500, estado: "resuelto", escalamiento: null, linea: MENSAJE_FINAL, final: true, celebrando: true },
  { t: 13000, celebrando: false },
  { t: 17000, fase: "calma", estado: "reposo", linea: "¿En qué te ayudo?", final: false, panel: false },
];

/** Vista del show en el milisegundo `t`. `vistaEn(Infinity)` es el estado final, el mismo al que lleva "Saltar". */
export function vistaEn(t: number): VistaShow {
  const b: Base = { ...BASE };
  for (const { t: momento, ...cambio } of LINEA_TIEMPO) if (momento <= t) Object.assign(b, cambio);
  const { llegados, escritas, listas, ...vista } = b;
  return {
    ...vista,
    casos: MENSAJES.slice(0, llegados).map((m, id) => ({ ...m, id, resuelto: m.fila < listas })),
    filas: FILAS.slice(0, escritas).map((f, i) => ({ ...f, lista: i < listas })),
  };
}

/** Movimiento reducido: el resultado completo y sin secuencia; se queda hasta que la persona lo cierre. */
export const VISTA_RESUMEN: VistaShow = {
  ...BASE,
  fase: "resumen",
  estado: "resuelto",
  linea: MENSAJE_FINAL,
  final: true,
  panel: true,
  casos: [],
  filas: FILAS.map((f) => ({ ...f, lista: true })),
};

interface Opciones {
  al: (vista: VistaShow) => void;
  signal: AbortSignal;
  sonido: () => boolean;
  alHablar: (hablando: boolean) => void;
}

/** Corre la línea de tiempo. Abortar la señal corta temporizadores, voz y tonos. `callar` solo silencia. */
export function correrShow({ al, signal, sonido, alHablar }: Opciones) {
  let contexto: AudioContext | null = null;
  let voz = new AbortController();
  let cola = Promise.resolve();
  let vozCaida = false;

  // Tonos generados: sin archivos de audio (ESTRUCTURA_FRONT.md §12).
  const tono = (hz: number, retraso = 0) => {
    try {
      contexto ??= new AudioContext();
      const inicio = contexto.currentTime + retraso;
      const osc = contexto.createOscillator();
      const vol = contexto.createGain();
      osc.frequency.value = hz;
      vol.gain.setValueAtTime(0.05, inicio);
      vol.gain.exponentialRampToValueAtTime(0.001, inicio + 0.12);
      osc.connect(vol).connect(contexto.destination);
      osc.start(inicio);
      osc.stop(inicio + 0.12);
    } catch {
      // Sin Web Audio el show sigue en silencio.
    }
  };

  // ponytail: la voz va en cola y puede atrasarse frente al reloj fijo; los subtítulos siempre van a tiempo.
  const decir = (linea: string) => {
    cola = cola.then(async () => {
      if (vozCaida || signal.aborted || voz.signal.aborted || !sonido()) return;
      alHablar(true);
      try {
        await hablar(linea, "female", voz.signal);
      } catch {
        vozCaida = true; // Clúster de voz caído: el show sigue con subtítulos.
      } finally {
        alHablar(false);
      }
    });
  };

  const efectos = (e: Evento) => {
    if (e.linea) decir(e.linea);
    if (!sonido()) return;
    if (e.llegados) tono(380 + e.llegados * 55);
    if (e.listas) tono(880);
    if (e.celebrando) [523, 659, 784].forEach((hz, i) => tono(hz, i * 0.1));
  };

  for (const evento of LINEA_TIEMPO) {
    const id = setTimeout(() => {
      al(vistaEn(evento.t));
      efectos(evento);
    }, evento.t);
    signal.addEventListener("abort", () => clearTimeout(id), { once: true });
  }
  signal.addEventListener(
    "abort",
    () => {
      voz.abort();
      void contexto?.close();
    },
    { once: true },
  );

  return {
    callar() {
      voz.abort();
      voz = new AbortController();
    },
  };
}
