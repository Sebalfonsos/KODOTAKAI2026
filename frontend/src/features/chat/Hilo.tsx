import { useEffect, useRef, type ReactNode } from "react";
import { Icono } from "../../components/ui/Icono";
import type { EstadoChat, TurnoAgente } from "../../state/chatStore";
import type { ContextoArtifact } from "../artifacts/AccionesArtifact";
import { Fuentes } from "../artifacts/cliente";
import { ArtifactView } from "../artifacts/registro";

/**
 * Orden de lectura: si pide datos, primero el texto y luego el formulario; si responde, la tarjeta y luego el texto.
 * Los chips siempre al final, porque son el "¿y ahora qué?".
 */
function TurnoAgenteVista({ turno: e, contexto }: { turno: TurnoAgente; contexto: ContextoArtifact }) {
  const chips = e.artifacts.filter((a) => a.tipo === "respuestas_rapidas");
  const tarjetas = e.artifacts.filter((a) => a.tipo !== "respuestas_rapidas");
  const pideDatos = tarjetas.some((a) => a.tipo.startsWith("formulario_"));
  // Al escalar, el texto del turno repite el mensaje del aviso: se muestra una sola vez.
  const texto = e.texto && !e.artifacts.some((a) => a.tipo === "aviso_escalamiento" && a.mensaje === e.texto) && <p className="burbuja__texto">{e.texto}</p>;
  return (
    <>
      {pideDatos && texto}
      {tarjetas.map((a) => (
        <ArtifactView key={a.id} artifact={a} contexto={contexto} />
      ))}
      {!pideDatos && texto}
      <Fuentes fuentes={e.citas} />
      {chips.map((a) => (
        <ArtifactView key={a.id} artifact={a} contexto={contexto} />
      ))}
    </>
  );
}

interface Props {
  estado: EstadoChat;
  contexto: ContextoArtifact;
  /** Lo que se muestra mientras la conversación está vacía. */
  vacio: ReactNode;
}

export function Hilo({ estado, contexto, vacio }: Props) {
  const final = useRef<HTMLDivElement>(null);
  const turnoFinal = useRef<HTMLElement>(null);

  // Se lee desde el inicio de la respuesta: un formulario o resultado largo no debe aterrizar en su final.
  // Solo al abrir el turno o al llegar otra tarjeta; los deltas de texto no mueven lo que el usuario está leyendo.
  const entradaFinal = estado.entradas.at(-1);
  const tarjetasFinal = entradaFinal?.rol === "agente" ? entradaFinal.artifacts.length : 0;
  useEffect(() => {
    if (!entradaFinal) return; // Sin mensajes no hay nada que seguir: el estado vacío se lee desde arriba.
    if (entradaFinal.rol === "agente") turnoFinal.current?.scrollIntoView({ block: "start" });
    else final.current?.scrollIntoView({ block: "end" });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `entradaFinal` cambia con cada delta.
  }, [estado.entradas.length, tarjetasFinal]);

  const esperandoTexto = estado.enCurso && (entradaFinal?.rol !== "agente" || (!entradaFinal.texto && !entradaFinal.artifacts.length));

  return (
    <div className="hilo" role="log" aria-live="polite" aria-label="Conversación con RUTI">
      {estado.entradas.length === 0 && vacio}
      {estado.entradas.map((e, i) =>
        e.rol === "agente" && e.acuse ? null : e.rol === "agente" ? (
          <article key={e.turnoId ?? i} ref={i === estado.entradas.length - 1 ? turnoFinal : undefined} className="burbuja burbuja--agente">
            <span className="burbuja__avatar" aria-hidden="true">
              <Icono nombre="chispa" tamano={16} />
            </span>
            <TurnoAgenteVista turno={e} contexto={contexto} />
          </article>
        ) : (
          <p key={i} className={`burbuja burbuja--${e.rol}`}>
            {e.rol === "asesor" && <strong>{e.autor ?? "Asesor"}: </strong>}
            {e.texto}
          </p>
        ),
      )}
      {esperandoTexto && (
        <p className="escribiendo">
          <span aria-hidden="true" />
          <span aria-hidden="true" />
          <span aria-hidden="true" />
          <span className="sr-only">RUTI está consultando</span>
        </p>
      )}
      <div ref={final} />
    </div>
  );
}
