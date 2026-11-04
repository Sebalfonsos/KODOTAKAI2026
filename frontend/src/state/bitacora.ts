import type { NombreIcono } from "../components/ui/Icono";
import type { TipoArtifact } from "../services/chat";
import type { TurnoAgente } from "./chatStore";

export interface Paso {
  texto: string;
  icono: NombreIcono;
  hecho: boolean;
}

const INTENCION: Record<string, string> = {
  saludo: "Entendí que me saludas",
  rastrear: "Entendí: rastrear un envío",
  cotizar: "Entendí: cotizar un flete",
  enviar: "Entendí: preparar un envío",
  mercancia: "Entendí: revisar una mercancía",
  embalaje: "Entendí: consulta de embalaje",
  cobertura: "Entendí: consulta de cobertura",
  pqrs_radicar: "Entendí: radicar una reclamación",
  pqrs_info: "Entendí: consulta sobre reclamaciones",
  asesor: "Entendí: quieres un asesor",
  fuera_de_alcance: "Eso está fuera de lo que manejo",
};

const ARTIFACT: Partial<Record<TipoArtifact, [string, NombreIcono]>> = {
  linea_tiempo_envio: ["Ubiqué tu envío", "camion"],
  mapa_ubicacion: ["Marqué la ubicación en el mapa", "pin"],
  estado_plazo: ["Revisé los plazos", "reloj"],
  resultado_cotizacion: ["Calculé la cotización", "calculadora"],
  veredicto_mercancia: ["Clasifiqué la mercancía", "escudo"],
  plan_envio: ["Armé el plan de envío", "ruta"],
  ficha_cobertura: ["Revisé la cobertura", "ruta"],
  guia_embalaje: ["Preparé la guía de embalaje", "caja"],
  checklist_documentos: ["Listé los documentos que necesitas", "documento"],
  formulario_cotizacion: ["Te dejé el formulario de cotización", "documento"],
  formulario_guia: ["Te pedí el número de guía", "documento"],
  formulario_pqrs: ["Te dejé el formulario de reclamación", "documento"],
  ticket_pqrs: ["Radiqué tu caso", "check"],
  aviso_escalamiento: ["Pedí un asesor humano", "asesor"],
  confirmacion: ["Confirmé la operación", "check"],
};

/** Qué hizo RUTI en un turno, en frases cortas. Sale de eventos reales del servidor, no del texto del modelo. */
export function bitacora(t: TurnoAgente): Paso[] {
  const pasos: Paso[] = [];
  const hecho = (texto: string, icono: NombreIcono) => pasos.push({ texto, icono, hecho: true });
  hecho(t.intencion ? (INTENCION[t.intencion] ?? "Entendí tu pregunta") : "Recibí tu mensaje", "chispa");
  if (t.latencias?.tool) hecho("Consulté los datos del sistema", "bodega");
  if (t.latencias?.retrieval) hecho("Busqué en la base de conocimiento", "lupa");
  for (const a of t.artifacts) {
    const r = ARTIFACT[a.tipo];
    if (r) hecho(...r);
  }
  if (t.citas.length) hecho(`Cité ${t.citas.length} ${t.citas.length === 1 ? "fuente" : "fuentes"}`, "documento");
  if (t.corregido) hecho("Corregí la respuesta tras verificarla", "escudo");
  else if (t.latencias?.verify) hecho("Verifiqué la respuesta", "check");
  if (!t.completo) pasos.push({ texto: "Trabajando…", icono: "reloj", hecho: false });
  return pasos;
}
