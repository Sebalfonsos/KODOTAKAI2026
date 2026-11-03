import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useLocation } from "react-router-dom";
import { Ruti, RutiStatus } from "../../components/ruti/Ruti";
import { useChat } from "../../hooks/useChat";
import { derivarRuti, turnoResuelto } from "../../state/rutiMachine";
import { ArtifactView } from "../artifacts/registro";

const RESUELTO_MS = 4000;
const ESCRITURA_MS = 2000;

/**
 * El mensaje inicial sale una vez por navegación. `location.key` sobrevive a la recarga: sin esto,
 * recargar /consultar repetiría "Quiero rastrear" en la conversación.
 */
function primeraVez(clave: string): boolean {
  try {
    if (sessionStorage.getItem(clave)) return false;
    sessionStorage.setItem(clave, "1");
  } catch {
    // Sin almacenamiento, el mensaje puede repetirse al recargar: es inofensivo.
  }
  return true;
}

export function Conversacion({ inicio, titulo }: { inicio?: string; titulo: string }) {
  const { estado, listo, enviar, reintentar, nueva } = useChat();
  const { key } = useLocation();
  const [texto, setTexto] = useState("");
  const [escribiendo, setEscribiendo] = useState(false);
  const [resueltoVigente, setResueltoVigente] = useState(false);
  const relojEscritura = useRef<number>(undefined);
  const final = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (inicio && listo && primeraVez(`translogix.inicio.${key}.${inicio}`)) {
      void enviar({ tipo: "texto", texto: inicio });
    }
  }, [inicio, listo, key, enviar]);

  const huboResultado = !estado.enCurso && turnoResuelto(estado);
  useEffect(() => {
    if (!huboResultado) return;
    setResueltoVigente(true);
    const t = setTimeout(() => setResueltoVigente(false), RESUELTO_MS);
    return () => clearTimeout(t);
  }, [huboResultado, estado.entradas.length]);

  useEffect(() => {
    final.current?.scrollIntoView({ block: "end" });
  }, [estado.entradas]);

  const vista = useMemo(
    () => derivarRuti({ chat: estado, escribiendo, resueltoVigente }),
    [estado, escribiendo, resueltoVigente],
  );

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

  const contexto = { enviar, bloqueado: estado.enCurso || !listo };

  return (
    <div className="conversacion">
      <h1 className="sr-only">{titulo}</h1>
      <aside className="conversacion__ruti">
        <Ruti vista={vista} encuadre="cabeza" />
        <RutiStatus mensaje={vista.mensaje} />
      </aside>

      <div className="conversacion__principal">
        <div className="hilo" role="log" aria-live="polite" aria-label="Conversación con RUTI">
          {estado.entradas.length === 0 && (
            <p className="hilo__vacio">Pregúntame por una guía, una cotización, una mercancía o un reclamo.</p>
          )}
          {estado.entradas.map((e, i) =>
            e.rol === "agente" ? (
              <article key={e.turnoId ?? i} className="burbuja burbuja--agente">
                {e.artifacts.map((a) => (
                  <ArtifactView key={a.id} artifact={a} contexto={contexto} />
                ))}
                {/* Al escalar, el texto del turno repite el mensaje del aviso: se muestra una sola vez. */}
                {e.texto && !e.artifacts.some((a) => a.tipo === "aviso_escalamiento" && a.mensaje === e.texto) && (
                  <p className="burbuja__texto">{e.texto}</p>
                )}
                {e.citas.length > 0 && (
                  <details className="fuentes">
                    <summary>Fuentes</summary>
                    <ul>
                      {e.citas.map((c) => (
                        <li key={`${c.doc_codigo}-${c.seccion}`}>
                          {c.documento}: {c.seccion}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </article>
            ) : (
              <p key={i} className={`burbuja burbuja--${e.rol}`}>
                {e.rol === "asesor" && <strong>{e.autor ?? "Asesor"}: </strong>}
                {e.texto}
              </p>
            ),
          )}
          <div ref={final} />
        </div>

        {estado.escalamiento?.fase === "resuelto" && (
          <div className="banda" role="status">
            El asesor cerró tu caso.{" "}
            <button type="button" className="boton boton--enlace" onClick={nueva}>
              Iniciar una conversación nueva
            </button>
          </div>
        )}

        {estado.fallo && (
          <div className="banda banda--error" role="alert">
            <span>
              <strong>{estado.fallo.titulo}</strong> {estado.fallo.detalle}
            </span>
            {estado.fallo.reintentable && (
              <button type="button" className="boton boton--secundario" onClick={reintentar}>
                Reintentar
              </button>
            )}
          </div>
        )}

        <form className="compositor" onSubmit={mandar}>
          <label htmlFor="mensaje" className="sr-only">
            Escribe tu mensaje
          </label>
          <textarea
            id="mensaje"
            rows={1}
            maxLength={2000}
            value={texto}
            placeholder="Escribe tu mensaje…"
            onChange={(e) => alEscribir(e.target.value)}
            onKeyDown={alTeclear}
          />
          <button className="boton boton--primario boton--fisico" disabled={estado.enCurso || !listo || !texto.trim()}>
            Enviar
          </button>
        </form>
      </div>
    </div>
  );
}
