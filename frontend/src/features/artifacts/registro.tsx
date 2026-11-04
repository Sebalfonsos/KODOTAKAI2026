import type { ComponentType } from "react";
import { Icono, type NombreIcono } from "../../components/ui/Icono";
import type { Artifact, TipoArtifact } from "../../services/chat";
import { AccionesArtifact, type ContextoArtifact } from "./AccionesArtifact";
import { AvisoEscalamiento } from "./AvisoEscalamiento";
import { Formulario } from "./Formulario";
import {
  ChecklistDocumentos,
  CitasArtifact,
  Confirmacion,
  EncuestaSatisfaccion,
  EstadoPlazo,
  FichaCobertura,
  GuiaEmbalaje,
  LineaTiempoEnvio,
  MapaUbicacion,
  ResultadoCotizacion,
  SoloAcciones,
  TicketPqrs,
  VeredictoMercancia,
} from "./cliente";
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
  // Cliente.
  linea_tiempo_envio: LineaTiempoEnvio,
  mapa_ubicacion: MapaUbicacion,
  resultado_cotizacion: ResultadoCotizacion,
  veredicto_mercancia: VeredictoMercancia,
  guia_embalaje: GuiaEmbalaje,
  ficha_cobertura: FichaCobertura,
  estado_plazo: EstadoPlazo,
  checklist_documentos: ChecklistDocumentos,
  ticket_pqrs: TicketPqrs,
  citas: CitasArtifact,
  respuestas_rapidas: SoloAcciones,
  confirmacion: Confirmacion,
  encuesta_satisfaccion: EncuestaSatisfaccion,
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
    <section className="artifact" aria-label={artifact.titulo ?? NOMBRE[artifact.tipo] ?? "Respuesta"} data-tipo={artifact.tipo}>
      {artifact.titulo && (
        <h2 className="artifact__titulo">
          {ICONO[artifact.tipo] && (
            <span className="artifact__icono">
              <Icono nombre={ICONO[artifact.tipo]!} tamano={18} />
            </span>
          )}
          {artifact.titulo}
        </h2>
      )}
      <Componente artifact={artifact} contexto={contexto} />
      {!PROPIAS_ACCIONES.has(artifact.tipo) && <AccionesArtifact artifact={artifact} contexto={contexto} />}
    </section>
  );
}

const ICONO: Partial<Record<TipoArtifact, NombreIcono>> = {
  formulario_cotizacion: "calculadora",
  formulario_guia: "codigo",
  formulario_pqrs: "documento",
  linea_tiempo_envio: "camion",
  mapa_ubicacion: "pin",
  resultado_cotizacion: "moneda",
  veredicto_mercancia: "escudo",
  guia_embalaje: "caja",
  ficha_cobertura: "ruta",
  estado_plazo: "reloj",
  checklist_documentos: "documento",
  ticket_pqrs: "check",
  aviso_escalamiento: "asesor",
  encuesta_satisfaccion: "estrella",
};

/** Nombre accesible cuando el servidor no envía `titulo`. */
const NOMBRE: Partial<Record<TipoArtifact, string>> = {
  linea_tiempo_envio: "Estado del envío",
  mapa_ubicacion: "Última ubicación",
  resultado_cotizacion: "Resultado de la cotización",
  veredicto_mercancia: "Veredicto de la mercancía",
  guia_embalaje: "Guía de embalaje",
  ficha_cobertura: "Cobertura",
  estado_plazo: "Plazo de la reclamación",
  checklist_documentos: "Documentos requeridos",
  ticket_pqrs: "Ticket de reclamación",
  respuestas_rapidas: "Respuestas sugeridas",
  encuesta_satisfaccion: "Encuesta de satisfacción",
};

/** Estos componentes pintan y ejecutan sus propias acciones (submit, carga de archivos, calificación). */
const PROPIAS_ACCIONES = new Set<TipoArtifact>([
  "formulario_cotizacion",
  "formulario_guia",
  "formulario_pqrs",
  "checklist_documentos",
  "encuesta_satisfaccion",
]);
