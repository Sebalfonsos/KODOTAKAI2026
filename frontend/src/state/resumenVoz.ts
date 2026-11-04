import type { Artifact } from "../services/chat";
import type { TurnoAgente } from "./chatStore";

/**
 * Lo que RUTI dice en voz alta: 1–2 frases con lo más importante, no la respuesta completa.
 * Sale de los datos estructurados del servidor (mismas cifras que la tarjeta en pantalla); si el turno no trae
 * ningún artifact resumible, se usa el inicio del texto.
 */

const MAX = 220;
const ZONA = "America/Bogota";
const DIA = new Intl.DateTimeFormat("es-CO", { weekday: "long", day: "numeric", month: "long", timeZone: ZONA });
const HORA = new Intl.DateTimeFormat("es-CO", { hour: "numeric", minute: "numeric", hourCycle: "h23", timeZone: ZONA });

/** "4 y 30 de la tarde": "4:30 p. m." trae puntos que cortan la frase al sintetizar. */
function horaHablada(d: Date): string {
  const partes = Object.fromEntries(HORA.formatToParts(d).map((p) => [p.type, p.value]));
  const h = Number(partes.hour);
  const m = Number(partes.minute);
  const periodo = h < 12 ? "de la mañana" : h < 19 ? "de la tarde" : "de la noche";
  return `${h % 12 || 12}${m ? ` y ${m}` : ""} ${periodo}`;
}

/** "32.000 pesos" se lee mejor que "$ 32.000". */
const pesos = (v: string) => `${Math.round(Number(v)).toLocaleString("es-CO")} pesos`;
const cuando = (iso: string) =>
  iso.length === 10 ? DIA.format(new Date(`${iso}T12:00:00`)) : `${DIA.format(new Date(iso))} a las ${horaHablada(new Date(iso))}`;
const horas = (h: number) => (h >= 48 && h % 24 === 0 ? `${h / 24} días` : `${h} horas`);
const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`;

const VEREDICTO = {
  permitido: "se puede enviar",
  restringido: "se puede enviar con condiciones",
  solo_ftl: "solo se puede enviar en camión dedicado",
  prohibido: "no se puede enviar",
} as const;

function deArtifact(a: Artifact): string | null {
  switch (a.tipo) {
    case "linea_tiempo_envio": {
      const critica = a.alerta?.nivel === "critica" ? ` Atención: ${a.alerta.mensaje}` : "";
      return `${a.estado_texto}${a.eta ? ` Llegada estimada: ${cuando(a.eta)}.` : ""}${critica}`;
    }
    case "resultado_cotizacion":
      return `El envío de ${a.origen} a ${a.destino} cuesta ${pesos(a.total)} y tarda unas ${horas(a.tiempo_estimado_horas)}.`;
    case "veredicto_mercancia": {
      const docs = a.documentos.length ? ` Necesitas ${plural(a.documentos.length, "documento", "documentos")}.` : "";
      // El paréntesis técnico ("(9, ONU 3480)") se ve en la tarjeta; leído en voz alta estorba.
      const producto = a.producto.replace(/\s*\([^)]*\)/g, "").trim();
      return `${producto.charAt(0).toUpperCase()}${producto.slice(1)}: ${VEREDICTO[a.veredicto]}.${docs}`;
    }
    case "ficha_cobertura":
      return `En ${a.municipio} tenemos ${a.tipo_cobertura.toLowerCase()}, con entrega en unas ${horas(a.tiempo_estandar_horas)}.`;
    case "guia_embalaje":
      return `Es mercancía de categoría ${a.categoria}. Te dejo ${plural(a.pasos.length, "paso", "pasos")} de embalaje en pantalla.`;
    case "estado_plazo":
      return a.vigente
        ? `Tu plazo sigue vigente: quedan ${plural(a.dias_habiles_restantes, "día hábil", "días hábiles")}.`
        : "El plazo para esta reclamación ya venció.";
    case "checklist_documentos": {
      const faltan = a.items.filter((i) => i.requerido && !i.completado).length;
      return faltan ? `Adjunta ${plural(faltan, "documento requerido", "documentos requeridos")} para radicar.` : null;
    }
    case "ticket_pqrs":
      return `Tu reclamación quedó radicada. Te respondemos a más tardar el ${cuando(a.fecha_limite_respuesta)}.`;
    case "aviso_escalamiento":
      return `Estoy solicitando un asesor. La espera estimada es de ${a.espera_estimada_s < 60 ? "menos de un minuto" : `unos ${Math.round(a.espera_estimada_s / 60)} minutos`}.`;
    case "confirmacion":
      return a.mensaje;
    default:
      return null;
  }
}

/** Primeras frases del texto, sin Markdown, cortadas en palabra completa. */
export function recortar(texto: string, max = MAX): string {
  const limpio = texto.replace(/[*#_`>|]/g, "").replace(/\s+/g, " ").trim();
  const oraciones = limpio.match(/[^.!?…]+[.!?…]*/g) ?? [];
  let salida = "";
  for (const o of oraciones.slice(0, 2)) {
    if (salida && salida.length + o.length > max) break;
    salida += o;
  }
  salida = salida.trim();
  if (salida.length <= max) return salida;
  return `${salida.slice(0, salida.lastIndexOf(" ", max)).trim()}…`;
}

export function resumirTurno(turno: Pick<TurnoAgente, "artifacts" | "texto">): string {
  // Los artifacts ya son frases cortas armadas aquí: no se recortan, para no perder una alerta crítica.
  for (const a of turno.artifacts) {
    const r = deArtifact(a);
    if (r) return r;
  }
  const texto = recortar(turno.texto);
  if (texto) return texto;
  return turno.artifacts.some((a) => a.tipo.startsWith("formulario_")) ? "Completa los datos en pantalla para continuar." : "";
}
