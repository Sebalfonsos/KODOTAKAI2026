import { Icono } from "../../components/ui/Icono";
import type { PropsArtifact } from "./registro";

const espera = (s: number) => (s < 60 ? `menos de 1 min` : `unos ${Math.round(s / 60)} min`);

/**
 * El `mensaje` es literal de `reglas_escalacion_humana.json`: no se reescribe.
 * Dice "solicitando", no "conectado": la conexión la confirma el primer mensaje del asesor.
 */
export function AvisoEscalamiento({ artifact }: PropsArtifact<"aviso_escalamiento">) {
  return (
    <div className="aviso" data-prioridad={artifact.prioridad}>
      <p className="aviso__titulo">
        <Icono nombre="asesor" tamano={20} />
        Solicitando un asesor
      </p>
      <p>{artifact.mensaje}</p>
      <p className="aviso__meta">
        Espera estimada: {espera(artifact.espera_estimada_s)}
        {artifact.posicion_cola != null && ` · Posición en la fila: ${artifact.posicion_cola}`}
      </p>
    </div>
  );
}
