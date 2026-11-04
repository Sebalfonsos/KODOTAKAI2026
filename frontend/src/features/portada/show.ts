import { crearSonido, type ModoVoz, type Sonido } from "./sonido";
import { prepararFractura, type Fractura, type Punto } from "./vidrio";
import { VISTA_REPOSO, type VistaShow } from "./vista";

// Demostración de la portada: es un guion etiquetado, no una conversación. No llama al chat ni inventa cifras,
// estados de envío o veredictos (ESTRUCTURA_FRONT.md §2, principios 2 y 7). Por eso aquí sí manda el reloj.

const FILAS = [
  { clave: "Rastreo", valor: "línea de tiempo del envío" },
  { clave: "Cotización", valor: "valor con su desglose" },
  { clave: "Dudas", valor: "respuesta con fuente citada" },
  { clave: "Reclamación", valor: "checklist de documentos" },
  { clave: "Asesor", valor: "traspaso con el historial" },
];

const NOMBRES = ["Marta G.", "Óscar P.", "Ana L.", "Julián R.", "Sofía C.", "Camilo T.", "Laura V.", "Diego M."];

/** Datos de ejemplo. `TLX-000123-CO` no existe en el dataset del TMS. Primero lo real; después se sale de control. */
const MENSAJES = [
  "¿Dónde está mi guía TLX-000123-CO?",
  "Ya van dos llamadas y nadie me dice dónde está mi envío.",
  "¿Cuánto me sale enviar 3 cajas de Bogotá a Cali?",
  "¿Puedo enviar pintura en aerosol?",
  "¿Cómo embalo una nevera?",
  "¿Tienen cobertura en mi municipio?",
  "Mi paquete llegó dañado. ¿Qué documentos necesito?",
  "Quiero hablar con una persona.",
  "¿Aló?",
  "¿Dónde está mi guía?",
  "Sumercé, ¿ya salió el camión?",
  "¿ALÓ?",
  "Vecino, ¿qué pasó con la nevera?",
  "Mi perro se comió la guía.",
  "¿Dónde está mi guía?",
  "HOLA HOLA HOLA",
  "¿Envían a la Luna?",
  "Le mando foto del paquete. Es una caja.",
  "Mi abuela dice que ya pasó el camión.",
  "¿DÓNDE ESTÁ MI GUÍA?",
  "Quiero cotizar una vaca.",
  "?",
  "Necesito la guía para ayer.",
  "¿Cuánto por enviarme a mí?",
  "??",
  "Se me olvidó la guía. ¿Cuál era?",
  "URGENTE",
  "¿La guía se come?",
  "???",
  "URGENTÍSIMO",
  "Lo mío es rapidito.",
  "¿Hay alguien ahí?",
  "Llamo otra vez en 5 minutos.",
  "¿Me repite la guía?",
  "¿ALÓOOOO?",
  "DÓNDE. ESTÁ. MI. GUÍA.",
];

export const TOTAL_CASOS = MENSAJES.length;

const MENSAJE_FINAL = "Lo repetitivo, resuelto. Lo delicado, con un asesor.";

type Efecto = "alarma" | "golpe" | "cinta" | "bocina" | "choque" | "reversa" | "acorde";

interface Base extends Omit<VistaShow, "casos" | "filas"> {
  llegados: number;
  escritas: number;
  listas: number;
}

type Evento = { t: number; efecto?: Efecto; voz?: ModoVoz; preparar?: boolean } & Partial<Base>;

const PRIMEROS = [300, 1000, 1600, 2100, 2500, 2850, 3150, 3400];
const AVALANCHA = TOTAL_CASOS - PRIMEROS.length;

/** Cada evento cambia solo lo que nombra. Los mensajes llegan cada vez más rápido: es la tensión del show. */
const EVENTOS: Evento[] = [
  { t: 0, fase: "activo", estado: "escuchando", linea: "A ver, ¿qué tenemos hoy?", voz: "normal" },
  ...PRIMEROS.map((t, i) => ({ t, llegados: i + 1 })),
  { t: 3800, estado: "pensando", linea: "Uno por uno, por favor.", voz: "normal" },
  { t: 5000, estado: "escuchando", temblor: 1, efecto: "alarma" },
  ...Array.from({ length: AVALANCHA }, (_, i) => ({
    t: Math.round(5000 + 4900 * ((i + 1) / AVALANCHA) ** 0.6),
    llegados: PRIMEROS.length + i + 1,
  })),
  { t: 7000, estado: "error", furia: true, temblor: 2, linea: "¡UNO!", grito: true, voz: "grito", golpes: 1, grietas: 1, efecto: "golpe" },
  { t: 7800, linea: "¡POR!", voz: "grito", golpes: 2, grietas: 2, efecto: "golpe" },
  { t: 8600, temblor: 3, linea: "¡UNO!", voz: "grito", golpes: 3, grietas: 3, efecto: "golpe" },
  { t: 9400, linea: "¡¡¡UNO POR UNO!!!", voz: "grito", golpes: 4, grietas: 6, efecto: "golpe" },
  // El silencio es parte del golpe: aquí se congela todo y se prepara el vidrio para que no se note el costo.
  { t: 10200, congelado: true, temblor: 0, linea: "…", grito: false, efecto: "cinta", preparar: true },
  { t: 11400, apagon: true, linea: "¿Preguntaban por la guía?", voz: "grave" },
  { t: 12800, camion: true, linea: "AHÍ LLEGÓ.", grito: true, voz: "grave", efecto: "bocina" },
  {
    t: 14400,
    roto: true,
    camion: false,
    apagon: false,
    congelado: false,
    furia: false,
    estado: "reposo",
    linea: "",
    grito: false,
    llegados: 0,
    grietas: 0,
    destellos: 1,
    efecto: "choque",
  },
  { t: 16800, linea: "Perdón. Me dejé llevar.", voz: "normal", hablando: true },
  { t: 18400, linea: "Ahora sí. Uno por uno.", voz: "normal", panel: true },
  { t: 18800, escritas: 1 },
  { t: 19300, listas: 1 },
  { t: 19500, escritas: 2 },
  { t: 20000, listas: 2 },
  { t: 20200, escritas: 3 },
  { t: 20700, listas: 3 },
  { t: 20900, escritas: 4 },
  { t: 21400, listas: 4 },
  {
    t: 21600,
    estado: "escalamiento",
    escalamiento: "transfiriendo",
    hablando: false,
    linea: "Esto amerita una persona. En una conversación real, te paso con un asesor.",
    voz: "normal",
  },
  { t: 22100, escritas: 5 },
  { t: 22900, listas: 5 },
  { t: 24000, estado: "reposo", escalamiento: null, hablando: true, panel: false, linea: "Y el vidrio lo recojo yo.", voz: "normal" },
  { t: 24900, recomponiendo: true, hablando: false, efecto: "reversa" },
  {
    t: 26150,
    roto: false,
    recomponiendo: false,
    estado: "resuelto",
    linea: MENSAJE_FINAL,
    final: true,
    celebrando: true,
    destellos: 2,
    efecto: "acorde",
  },
  { t: 28000, celebrando: false },
  { t: 31000, fase: "calma", estado: "reposo", linea: "¿En qué te ayudo?", final: false },
];

export const LINEA_TIEMPO = [...EVENTOS].sort((a, b) => a.t - b.t);

/** Vista del show en el milisegundo `t`. `vistaEn(Infinity)` es el estado final, el mismo al que lleva "Saltar". */
export function vistaEn(t: number): VistaShow {
  const { casos: _c, filas: _f, ...inicial } = VISTA_REPOSO;
  const b: Base = { ...inicial, llegados: 0, escritas: 0, listas: 0 };
  for (const { t: momento, efecto: _e, voz: _v, preparar: _p, ...cambio } of LINEA_TIEMPO) if (momento <= t) Object.assign(b, cambio);
  const { llegados, escritas, listas, ...vista } = b;
  return {
    ...vista,
    casos: MENSAJES.slice(0, llegados).map((texto, id) => {
      const quien = NOMBRES[id % NOMBRES.length];
      return { id, texto, quien, iniciales: quien.replace(/[^A-ZÓ]/g, "") };
    }),
    filas: FILAS.slice(0, escritas).map((f, i) => ({ ...f, lista: i < listas })),
  };
}

/** Movimiento reducido: sin destrucción. El resultado completo se queda hasta que la persona lo cierre. */
export const VISTA_RESUMEN: VistaShow = {
  ...VISTA_REPOSO,
  fase: "resumen",
  estado: "resuelto",
  linea: MENSAJE_FINAL,
  final: true,
  panel: true,
  filas: FILAS.map((f) => ({ ...f, lista: true })),
};

interface Opciones {
  al: (vista: VistaShow) => void;
  signal: AbortSignal;
  raiz: () => HTMLElement | null;
  impacto: Punto;
  sonido: () => boolean;
}

/** Corre la línea de tiempo. Abortar la señal corta temporizadores, sonido y vidrio. */
export function correrShow({ al, signal, raiz, impacto, sonido }: Opciones) {
  let kit: Sonido | null = null;
  try {
    const ctx = new AudioContext();
    ctx.resume().catch(() => undefined);
    kit = crearSonido(ctx);
    kit.silenciar(!sonido());
  } catch {
    // Sin Web Audio el show sigue en silencio: los subtítulos cuentan la historia.
  }
  let fractura: Fractura | null = null;
  let pararAlarma: (() => void) | null = null;
  const quitarFractura = () => {
    fractura?.quitar();
    fractura = null;
  };

  const aplicar = (e: Evento) => {
    if (e.preparar) {
      const nodo = raiz();
      if (nodo) fractura = prepararFractura(nodo, impacto);
    }
    if (e.roto) fractura?.romper();
    if (e.recomponiendo) fractura?.recomponer();
    if (e.llegados) kit?.ding(e.llegados);
    if (e.grietas) kit?.grieta();
    if (e.listas) kit?.ding(30);
    if (e.linea && e.voz) kit?.hablar(e.linea, e.voz);
    if (e.efecto === "alarma") pararAlarma = kit?.alarma() ?? null;
    if (e.efecto === "golpe") kit?.golpe();
    if (e.efecto === "cinta") {
      pararAlarma?.();
      kit?.cinta();
    }
    if (e.efecto === "bocina") kit?.bocina(1.6);
    if (e.efecto === "choque") kit?.choque();
    if (e.efecto === "reversa") kit?.reversa(1.25);
    if (e.efecto === "acorde") kit?.acorde();
  };

  const fin = LINEA_TIEMPO.at(-1)?.t ?? 0;
  for (const evento of LINEA_TIEMPO) {
    const id = setTimeout(() => {
      aplicar(evento);
      al(vistaEn(evento.t));
      // Dos cuadros: primero se pinta la página real debajo y solo después se retira el vidrio, sin parpadeo.
      if (evento.roto === false) requestAnimationFrame(() => requestAnimationFrame(quitarFractura));
      if (evento.t === fin) kit?.cerrar();
    }, evento.t);
    signal.addEventListener("abort", () => clearTimeout(id), { once: true });
  }
  signal.addEventListener(
    "abort",
    () => {
      quitarFractura();
      kit?.cerrar();
    },
    { once: true },
  );

  return { silenciar: (s: boolean) => kit?.silenciar(s) };
}
