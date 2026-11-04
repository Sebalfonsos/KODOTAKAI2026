import { Icono } from "../../components/ui/Icono";
import type { Conversacion } from "../../hooks/useConversacion";

interface Props {
  conversacion: Conversacion;
  idEntrada: string;
  /** En modo agente el micrófono es el orbe de la llamada: un segundo botón competiría por `voz.nivel`. */
  sinMic?: boolean;
}

/** Avisos de la conversación y barra de entrada con micrófono. */
export function Compositor({ conversacion: c, idEntrada, sinMic }: Props) {
  const { estado, listo, voz, texto } = c;
  const conAsesor = estado.escalamiento?.fase === "transfiriendo" || estado.escalamiento?.fase === "conectado";
  const estadoMic = voz.grabando
    ? "Escuchando: toca para enviar"
    : voz.preparando
      ? "Preparando el micrófono…"
      : voz.transcribiendo
        ? "Transcribiendo…"
        : conAsesor
          ? "Hablarle a tu asesor"
          : "Hablar con RUTI";

  return (
    <>
      {estado.escalamiento?.fase === "transfiriendo" && (
        <div className="banda banda--asesor" role="status">
          <Icono nombre="reloj" tamano={18} />
          Esperando a un asesor. Lo que escribas le llegará directamente.
        </div>
      )}
      {estado.escalamiento?.fase === "conectado" && (
        <div className="banda banda--asesor" role="status">
          <Icono nombre="asesor" tamano={18} />
          Estás hablando con un asesor. RUTI vuelve cuando cierre tu caso.
        </div>
      )}
      {estado.escalamiento?.fase === "resuelto" && (
        <div className="banda" role="status">
          El asesor cerró tu caso.{" "}
          <button type="button" className="boton boton--enlace" onClick={c.nueva}>
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
            <button type="button" className="boton boton--secundario" onClick={c.reintentar}>
              Reintentar
            </button>
          )}
        </div>
      )}

      {voz.aviso && (
        <div className="banda banda--voz" role="status">
          <span>{voz.aviso}</span>
          <button type="button" className="boton boton--enlace" onClick={voz.cerrarAviso}>
            Entendido
          </button>
        </div>
      )}

      <form className="compositor" onSubmit={c.mandar}>
        {voz.microfonoDisponible && !sinMic && (
          <button
            type="button"
            className="boton boton--icono boton--mic"
            ref={voz.nivel}
            data-grabando={voz.grabando || undefined}
            data-ocupado={voz.preparando || voz.transcribiendo || undefined}
            aria-pressed={voz.grabando}
            aria-label={estadoMic}
            title={estadoMic}
            disabled={voz.transcribiendo || (!voz.grabando && !voz.preparando && (estado.enCurso || !listo))}
            onPointerDown={c.mic.alPresionar}
            onPointerUp={c.mic.alSoltar}
            onPointerCancel={c.mic.alSoltar}
            onClick={c.mic.alClicTeclado}
            onContextMenu={(e) => e.preventDefault()}
          >
            <Icono nombre={voz.grabando ? "detener" : "mic"} />
          </button>
        )}
        <label htmlFor={idEntrada} className="sr-only">
          Escribe tu mensaje
        </label>
        <textarea
          id={idEntrada}
          rows={1}
          maxLength={2000}
          value={texto}
          placeholder={
            voz.grabando
              ? "Habla ahora… envío cuando termines"
              : voz.preparando
                ? "Preparando el micrófono…"
                : voz.transcribiendo
                  ? "Entendiendo lo que dijiste…"
                  : conAsesor
                    ? "Escribe o habla con tu asesor…"
                    : "Escribe o habla con RUTI…"
          }
          onChange={(e) => c.alEscribir(e.target.value)}
          onKeyDown={c.alTeclear}
        />
        <button className="boton boton--primario boton--fisico" disabled={estado.enCurso || !listo || !texto.trim()} aria-label="Enviar">
          <Icono nombre="flecha" />
        </button>
      </form>
    </>
  );
}
