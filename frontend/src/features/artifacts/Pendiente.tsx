import type { TipoArtifact } from "../../services/chat";
import type { PropsArtifact } from "./registro";

/** Marcador de desarrollo: hace visible qué tipo llegó y aún no tiene componente. No debe quedar en la demo. */
export function Pendiente<T extends TipoArtifact>({ artifact }: PropsArtifact<T>) {
  return (
    <details className="pendiente">
      <summary>Componente pendiente: {artifact.tipo}</summary>
      <pre>{JSON.stringify(artifact, null, 2)}</pre>
    </details>
  );
}
