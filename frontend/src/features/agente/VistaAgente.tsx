import { useEffect, useRef, useState } from "react";
import { Ruti, RutiStatus } from "../../components/ruti/Ruti";
import { Icono } from "../../components/ui/Icono";
import type { Conversacion } from "../../hooks/useConversacion";
import { bitacora } from "../../state/bitacora";
import type { TurnoAgente } from "../../state/chatStore";
import type { VistaRuti } from "../../state/rutiMachine";
import type { ContextoArtifact } from "../artifacts/AccionesArtifact";
import { Fuentes } from "../artifacts/cliente";
import { ArtifactView } from "../artifacts/registro";
import { Compositor } from "../chat/Compositor";
import { CASOS } from "./casos";

// ponytail: pausa fija para que la lectura del turno alcance a empezar antes de reabrir el micrófono
// (si arrancara antes, RUTI se grabaría a sí misma). Subirla si la voz tarda más en arrancar.
const ESPERA_ESCUCHA_MS = 500;

function Turno({ turno, contexto, ultimo }: { turno: TurnoAgente; contexto: ContextoArtifact; ultimo: boolean }) {
  const tarjetas = turno.artifacts.filter((a) => a.tipo !== "respuestas_rapidas");
  const chips = ultimo ? turno.artifacts.filter((a) => a.tipo === "respuestas_rapidas") : [];
  return (
    <>
      <ol className="bitacora" aria-label="Lo que hizo RUTI">
        {bitacora(turno).map((p, i) => (
          <li key={i} data-hecho={p.hecho || undefined}>
            <span className="bitacora__icono" aria-hidden="true">
              <Icono nombre={p.icono} tamano={16} />
            </span>
            {p.texto}
          </li>
        ))}
      </ol>
      {tarjetas.map((a) => (
        <ArtifactView key={a.id} artifact={a} contexto={contexto} />
      ))}
      {turno.texto && (
        <details className="bitacora__texto">
          <summary>Ver respuesta escrita</summary>
          <p>{turno.texto}</p>
          <Fuentes fuentes={turno.citas} />
        </details>
      )}
      {chips.map((a) => (
        <ArtifactView key={a.id} artifact={a} contexto={contexto} />
      ))}
    </>
  );
}

/**
 * Modo agente a pantalla completa: una "llamada" manos libres con RUTI. La voz dice un resumen corto
 * (`resumirTurno`), la bitácora cuenta qué hizo (eventos del servidor) y el texto escrito queda plegado.
 */
export function VistaAgente({ conversacion: c, vista }: { conversacion: Conversacion; vista: VistaRuti }) {
  const { estado, listo, enviar, voz, empezarDictado } = c;
  const { cancelar, callar } = voz;
  const [activo, setActivo] = useState(false);
  const turnoFinal = useRef<HTMLDivElement>(null);

  const ultimo = estado.entradas.at(-1);
  const conAsesor = !!estado.escalamiento && estado.escalamiento.fase !== "resuelto";
  const pideDatos = ultimo?.rol === "agente" && ultimo.completo && ultimo.artifacts.some((a) => a.tipo.startsWith("formulario_"));
  const libre = listo && !estado.enCurso && !voz.grabando && !voz.preparando && !voz.transcribiendo && !voz.hablando;
  // Se pausa sola cuando hablar no sirve: un formulario por llenar, un asesor humano, un fallo o un aviso del micrófono.
  const pausar = !!voz.aviso || !!estado.fallo || conAsesor || (pideDatos && libre);

  useEffect(() => {
    if (activo && pausar) setActivo(false);
  }, [activo, pausar]);

  useEffect(() => {
    if (!activo || pausar || !libre) return;
    const t = window.setTimeout(empezarDictado, ESPERA_ESCUCHA_MS);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `empezarDictado` es nuevo en cada render.
  }, [activo, pausar, libre]);

  // Salir del modo agente corta el micrófono y la lectura.
  useEffect(
    () => () => {
      cancelar();
      callar();
    },
    [cancelar, callar],
  );

  const tarjetas = ultimo?.rol === "agente" ? ultimo.artifacts.length : 0;
  useEffect(() => {
    turnoFinal.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [estado.entradas.length, tarjetas]);

  // Colgar descarta lo que se estaba grabando; retomar interrumpe a RUTI y escucha de inmediato.
  const alternar = () => {
    callar();
    if (activo) {
      setActivo(false);
      cancelar();
      return;
    }
    voz.cerrarAviso();
    if (!voz.leer) voz.setLeer(true);
    setActivo(true);
  };

  const etiqueta = voz.grabando
    ? "Te escucho…"
    : voz.preparando
      ? "Preparando el micrófono…"
      : voz.transcribiendo || estado.enCurso
        ? "Pensando…"
        : voz.hablando
          ? "RUTI está hablando"
          : activo
            ? "En llamada"
            : estado.entradas.length
              ? "En pausa: toca para seguir"
              : "Toca para hablar con RUTI";

  const contexto: ContextoArtifact = { enviar, bloqueado: estado.enCurso || !listo };
  const indiceFinal = estado.entradas.length - 1;

  return (
    <div className="vista-agente">
      <section className="vista-agente__escenario" aria-label="Llamada con RUTI">
        <Ruti vista={vista} encuadre="completo" hablando={voz.hablando} className="vista-agente__ruti" />
        <RutiStatus mensaje={voz.transcribiendo ? "Entendiendo lo que dijiste…" : vista.mensaje} />
        {voz.microfonoDisponible ? (
          <button
            type="button"
            ref={voz.nivel}
            className="orbe"
            aria-pressed={activo}
            aria-label={activo ? "Terminar la llamada con RUTI" : "Empezar la llamada con RUTI"}
            data-activo={activo || undefined}
            data-grabando={voz.grabando || undefined}
            data-hablando={voz.hablando || undefined}
            data-pensando={voz.transcribiendo || estado.enCurso || undefined}
            disabled={!listo}
            onClick={alternar}
          >
            <span className="orbe__ondas" aria-hidden="true" />
            <Icono nombre={activo ? "detener" : "mic"} tamano={36} />
          </button>
        ) : (
          <p className="nota">Tu navegador no permite usar el micrófono: escríbeme abajo.</p>
        )}
        <p className="orbe__estado" aria-live="polite">
          {etiqueta}
        </p>
      </section>

      <section className="vista-agente__actividad" aria-label="Lo que va haciendo RUTI">
        <div className="vista-agente__registro" role="log" aria-live="polite">
          {estado.entradas.length === 0 && (
            <div className="agente__vacio">
              <p>
                <strong>Toca el micrófono y dime qué quieres hacer.</strong>
                <br />
                Aquí verás, paso a paso, lo que voy haciendo.
              </p>
              <h3>Casos de estudio</h3>
              <ul className="agente__casos">
                {CASOS.map((caso) => (
                  <li key={caso.dicho}>
                    <button type="button" className="sugerencia" disabled={!listo} onClick={() => void enviar({ tipo: "texto", texto: caso.dicho })}>
                      <span className="sugerencia__icono">
                        <Icono nombre={caso.icono} tamano={18} />
                      </span>
                      <span className="agente__caso">
                        <strong>{caso.titulo}</strong>
                        <span>«{caso.dicho}»</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {estado.entradas.map((e, i) =>
            e.rol === "agente" && e.acuse ? null : (
              <div key={e.rol === "agente" ? (e.turnoId ?? i) : i} ref={i === indiceFinal ? turnoFinal : undefined} className="vista-agente__paso">
                {e.rol === "agente" ? (
                  <Turno turno={e} contexto={contexto} ultimo={i === indiceFinal} />
                ) : (
                  <p className={`vista-agente__dicho vista-agente__dicho--${e.rol}`}>
                    {e.rol === "asesor" ? <strong>{e.autor ?? "Asesor"}: </strong> : <span className="sr-only">Tú: </span>}
                    {e.texto}
                  </p>
                )}
              </div>
            ),
          )}
          {estado.enCurso && ultimo?.rol !== "agente" && (
            <ol className="bitacora">
              <li>
                <span className="bitacora__icono" aria-hidden="true">
                  <Icono nombre="reloj" tamano={16} />
                </span>
                Trabajando…
              </li>
            </ol>
          )}
        </div>
        <Compositor conversacion={c} idEntrada="mensaje-agente" sinMic />
      </section>
    </div>
  );
}
