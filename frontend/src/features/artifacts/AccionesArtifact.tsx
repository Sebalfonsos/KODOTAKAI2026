import type { Accion, Artifact, MensajeEntrada } from "../../services/chat";
import { json } from "../../services/http";

export interface ContextoArtifact {
  enviar: (cuerpo: MensajeEntrada, ruta?: string) => Promise<void>;
  bloqueado: boolean;
}

/** Acciones genéricas de un artifact (docs/frontend.md §5). `submit` lo resuelve el formulario. */
export function AccionesArtifact({ artifact, contexto }: { artifact: Artifact; contexto: ContextoArtifact }) {
  const acciones = artifact.acciones.filter((a: Accion) => a.tipo !== "submit");
  if (!acciones.length) return null;
  const ejecutar = (a: Accion) => {
    if (a.tipo === "mensaje" && a.mensaje) void contexto.enviar({ tipo: "texto", texto: a.mensaje });
    else if (a.tipo === "enlace" && a.endpoint) {
      void json(a.endpoint, a.metodo === "POST" ? (a.payload ?? {}) : undefined);
    }
  };
  return (
    <div className="artifact__acciones">
      {acciones.map((a: Accion) => (
        <button
          key={a.id}
          type="button"
          className={`boton boton--${a.estilo ?? "primario"}`}
          disabled={contexto.bloqueado}
          onClick={() => ejecutar(a)}
        >
          {a.etiqueta}
        </button>
      ))}
    </div>
  );
}
