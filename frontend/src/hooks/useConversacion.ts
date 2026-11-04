import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type MouseEvent, type PointerEvent } from "react";
import type { MensajeEntrada } from "../services/chat";
import { resumirTurno } from "../state/resumenVoz";
import { useChat } from "./useChat";
import { useVoz } from "./useVoz";

const ESCRITURA_MS = 2000;
/** Presión más larga que esto es "mantener para hablar": soltar envía. */
const MANTENER_MS = 450;

/** Chat, voz y compositor de una conversación: lo comparten las páginas de servicio y el modo agente. */
export function useConversacion(servicio: string) {
  const { estado, listo, enviar: enviarChat, reintentar, nueva } = useChat(servicio);
  const voz = useVoz();
  const { callar, decir, leer } = voz;
  // Un mensaje nuevo (texto, voz, chip o formulario) interrumpe la lectura anterior.
  const enviar = useCallback(
    (cuerpo: MensajeEntrada, ruta?: string) => {
      callar();
      return enviarChat(cuerpo, ruta);
    },
    [callar, enviarChat],
  );
  const leidos = useRef<Set<string> | null>(null);
  const [texto, setTexto] = useState("");
  const [escribiendo, setEscribiendo] = useState(false);
  const relojEscritura = useRef<number>(undefined);

  // RUTI lee en voz alta un resumen de cada respuesta nueva. Lo recuperado del historial no se lee.
  useEffect(() => {
    if (!listo || estado.enCurso) return;
    const claves = estado.entradas.flatMap((e, i) => (e.rol === "agente" && e.completo ? [e.turnoId ?? `i${i}`] : []));
    if (!leidos.current) {
      leidos.current = new Set(claves);
      return;
    }
    const ultimo = estado.entradas.at(-1);
    const clave = claves.at(-1);
    if (!clave || leidos.current.has(clave) || ultimo?.rol !== "agente") return;
    leidos.current.add(clave);
    if (leer && !ultimo.acuse) void decir(resumirTurno(ultimo));
  }, [listo, estado.enCurso, estado.entradas, leer, decir]);

  const alEscribir = (valor: string) => {
    setTexto(valor);
    setEscribiendo(valor.length > 0);
    window.clearTimeout(relojEscritura.current);
    relojEscritura.current = window.setTimeout(() => setEscribiendo(false), ESCRITURA_MS);
  };

  const mandar = (e?: FormEvent) => {
    e?.preventDefault();
    const limpio = texto.trim();
    if (!limpio || estado.enCurso || !listo) return;
    setTexto("");
    setEscribiendo(false);
    void enviar({ tipo: "texto", texto: limpio });
  };

  const alTeclear = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) mandar(e);
  };

  // El dictado termina segundos después de empezar: se lee el estado vigente, no el del momento del toque.
  const alDictado = useRef<(dicho: string) => void>(() => undefined);
  alDictado.current = (dicho) => {
    if (!estado.enCurso && listo) void enviar({ tipo: "texto", texto: dicho });
    else setTexto(dicho);
  };
  const pulsado = useRef(0);
  const empezarDictado = () => void voz.iniciar((dicho) => alDictado.current(dicho));
  /** Toque: graba y corta sola al callarte (o con otro toque). Mantener presionado: corta al soltar. */
  const alPresionar = (e: PointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return;
    if (voz.grabando) {
      pulsado.current = 0;
      voz.detener();
      return;
    }
    pulsado.current = performance.now();
    empezarDictado();
  };
  const alSoltar = () => {
    if (pulsado.current && performance.now() - pulsado.current > MANTENER_MS) voz.detener();
    pulsado.current = 0;
  };
  // Teclado (Enter/Espacio llegan como clic sin puntero).
  const alClicTeclado = (e: MouseEvent<HTMLButtonElement>) => {
    if (e.detail !== 0) return;
    if (voz.grabando) voz.detener();
    else empezarDictado();
  };

  return {
    estado,
    listo,
    enviar,
    reintentar,
    nueva,
    voz,
    texto,
    escribiendo,
    alEscribir,
    mandar,
    alTeclear,
    mic: { alPresionar, alSoltar, alClicTeclado },
  };
}

export type Conversacion = ReturnType<typeof useConversacion>;
