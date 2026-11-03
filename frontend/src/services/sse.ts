/** Lector del protocolo SSE del chat (docs/frontend.md §4.2). `EventSource` no sirve: hay POST y cabecera Authorization. */
export interface EventoSSE {
  evento: string;
  data: unknown;
}

/** Extrae los eventos completos del búfer y devuelve lo que aún no llega entero. */
export function extraerEventos(bufer: string): { eventos: EventoSSE[]; resto: string } {
  const eventos: EventoSSE[] = [];
  const normalizado = bufer.replace(/\r\n/g, "\n");
  let resto = normalizado;
  let corte: number;
  while ((corte = resto.indexOf("\n\n")) >= 0) {
    const bloque = resto.slice(0, corte);
    resto = resto.slice(corte + 2);
    let evento = "message";
    const lineas: string[] = [];
    for (const linea of bloque.split("\n")) {
      if (linea.startsWith(":")) continue; // keep-alive
      if (linea.startsWith("event:")) evento = linea.slice(6).trim();
      else if (linea.startsWith("data:")) lineas.push(linea.slice(5).trim());
    }
    if (lineas.length) eventos.push({ evento, data: JSON.parse(lineas.join("\n")) });
  }
  return { eventos, resto };
}

/** El stream dejó de enviar datos y keep-alives: la conexión está muerta aunque nadie la haya cerrado. */
export class ErrorSilencio extends Error {}

export async function leerStream(
  cuerpo: ReadableStream<Uint8Array>,
  alEvento: (e: EventoSSE) => void,
  silencioMaxMs?: number,
): Promise<void> {
  const lector = cuerpo.getReader();
  const decodificador = new TextDecoder(); // `stream: true` respeta tildes partidas entre fragmentos.
  let bufer = "";
  for (;;) {
    const { value, done } = await leerConLimite(lector, silencioMaxMs);
    if (done) return;
    bufer += decodificador.decode(value, { stream: true });
    const { eventos, resto } = extraerEventos(bufer);
    bufer = resto;
    eventos.forEach(alEvento);
  }
}

async function leerConLimite(lector: ReadableStreamDefaultReader<Uint8Array>, limiteMs?: number) {
  if (!limiteMs) return lector.read();
  let reloj: ReturnType<typeof setTimeout> | undefined;
  const vencido = new Promise<never>((_, rechazar) => {
    reloj = setTimeout(() => {
      // En este orden: cancelar resuelve la lectura pendiente y parecería un cierre normal.
      rechazar(new ErrorSilencio("La respuesta dejó de llegar."));
      void lector.cancel();
    }, limiteMs);
  });
  try {
    return await Promise.race([lector.read(), vencido]);
  } finally {
    clearTimeout(reloj);
  }
}
