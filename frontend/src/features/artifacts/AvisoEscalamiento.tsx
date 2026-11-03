import type { PropsArtifact } from "./registro";

/** El `mensaje` es literal de `reglas_escalacion_humana.json`: no se reescribe. */
export function AvisoEscalamiento({ artifact }: PropsArtifact<"aviso_escalamiento">) {
  return (
    <div className="aviso" data-prioridad={artifact.prioridad}>
      <p>{artifact.mensaje}</p>
      <p className="aviso__meta">
        Espera estimada: {artifact.espera_estimada_s} s
        {artifact.posicion_cola != null && ` · Posición en la fila: ${artifact.posicion_cola}`}
      </p>
    </div>
  );
}
