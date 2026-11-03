import type { ComponentType } from "react";
import type { Artifact, TipoArtifact } from "../../services/chat";
import { AccionesArtifact, type ContextoArtifact } from "./AccionesArtifact";
import { AvisoEscalamiento } from "./AvisoEscalamiento";
import { Formulario } from "./Formulario";
import { Pendiente } from "./Pendiente";

export interface PropsArtifact<T extends TipoArtifact = TipoArtifact> {
  artifact: Extract<Artifact, { tipo: T }>;
  contexto: ContextoArtifact;
}

/**
 * Un componente por tipo de artifact. Al ser un `Record` sobre la unión generada desde OpenAPI, TypeScript
 * falla si el contrato añade un tipo y aquí falta. `Pendiente` marca lo que aún no se ha construido.
 */
const REGISTRO: { [T in TipoArtifact]: ComponentType<PropsArtifact<T>> } = {
  // Formularios del servidor: comparten renderizador.
  formulario_cotizacion: Formulario,
  formulario_guia: Formulario,
  formulario_pqrs: Formulario,
  // Escalamiento.
  aviso_escalamiento: AvisoEscalamiento,
  // Cliente: fase 4 a 8 del plan.
  linea_tiempo_envio: Pendiente,
  mapa_ubicacion: Pendiente,
  resultado_cotizacion: Pendiente,
  veredicto_mercancia: Pendiente,
  guia_embalaje: Pendiente,
  ficha_cobertura: Pendiente,
  estado_plazo: Pendiente,
  checklist_documentos: Pendiente,
  ticket_pqrs: Pendiente,
  citas: Pendiente,
  respuestas_rapidas: Pendiente,
  confirmacion: Pendiente,
  encuesta_satisfaccion: Pendiente,
  // Administración: panel /admin.
  tarjetas_kpi: Pendiente,
  grafico: Pendiente,
  tabla_datos: Pendiente,
  tarjeta_prediccion: Pendiente,
  metricas_modelo: Pendiente,
  cola_escalamientos: Pendiente,
};

export function ArtifactView({ artifact, contexto }: { artifact: Artifact; contexto: ContextoArtifact }) {
  const Componente = REGISTRO[artifact.tipo] as ComponentType<PropsArtifact> | undefined;
  if (!Componente) {
    // Versión futura del contrato: se ignora con elegancia; el texto del turno sigue visible (§5 de la guía).
    console.warn("Artifact desconocido", artifact);
    return null;
  }
  return (
    <section className="artifact" aria-label={artifact.titulo ?? artifact.tipo} data-tipo={artifact.tipo}>
      {artifact.titulo && <h2 className="artifact__titulo">{artifact.titulo}</h2>}
      <Componente artifact={artifact} contexto={contexto} />
      {!esFormulario(artifact.tipo) && <AccionesArtifact artifact={artifact} contexto={contexto} />}
    </section>
  );
}

const esFormulario = (t: TipoArtifact) => t.startsWith("formulario_");
