import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type MouseEvent, type PointerEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Ruti, RutiStatus } from "../../components/ruti/Ruti";
import { Icono, type NombreIcono } from "../../components/ui/Icono";
import { useChat } from "../../hooks/useChat";
import { useVoz } from "../../hooks/useVoz";
import type { TurnoAgente } from "../../state/chatStore";
import { resumirTurno } from "../../state/resumenVoz";
import { derivarRuti, turnoResuelto } from "../../state/rutiMachine";
import type { MensajeEntrada, TipoArtifact } from "../../services/chat";
import { Fuentes } from "../artifacts/cliente";
import type { ContextoArtifact } from "../artifacts/AccionesArtifact";
import { ArtifactView } from "../artifacts/registro";

const RESUELTO_MS = 4000;
const ESCRITURA_MS = 2000;
/** Presión más larga que esto es "mantener para hablar": soltar envía. */
const MANTENER_MS = 450;

/** Mismas sugerencias de la propuesta (§4.6): cada una es un mensaje normal. */
const SUGERENCIAS: { texto: string; icono: NombreIcono }[] = [
  { texto: "¿Dónde está mi paquete?", icono: "caja" },
  { texto: "¿Cuánto cuesta un envío?", icono: "calculadora" },
  { texto: "¿Puedo transportar esta mercancía?", icono: "escudo" },
  { texto: "Necesito presentar una reclamación", icono: "alerta" },
];

/** El último paso se marca solo cuando llega el artifact que confirma el resultado del flujo. */
export interface Pasos {
  nombres: readonly [string, string, string];
  resultado: TipoArtifact;
}

interface Props {
  inicio?: string;
  titulo: string;
  /** Flujos guiados: Datos → Consultando → Resultado, derivado del estado real del chat. */
  pasos?: Pasos;
  /** Aviso fijo bajo el encabezado (p. ej. iniciar sesión para radicar). */
  aviso?: ReactNode;
  icono?: NombreIcono;
  /** Una línea que dice qué obtiene el usuario en este servicio. */
  descripcion?: string;
}

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

export function Conversacion({ inicio, titulo, pasos, aviso, icono = "chat", descripcion }: Props) {
  const { estado, listo, enviar: enviarChat, reintentar, nueva } = useChat(inicio ?? "ayuda");
  const voz = useVoz();
  const { callar, decir, leer } = voz;
  // Un mensaje nuevo (texto, voz, chip o formulario) interrumpe la lectura anterior.
  const enviar = useCallback(
    (cuerpo: MensajeEntrada, ruta?: string) => {
      callar();
      return enviarChat(cuerpo, ruta);
    },
    [callar, enviarChat],
  );
  const leidos = useRef<Set<string> | null>(null);
  const inicioEnviado = useRef(false);
  const [texto, setTexto] = useState("");
  const [escribiendo, setEscribiendo] = useState(false);
  const [resueltoVigente, setResueltoVigente] = useState(false);
  const relojEscritura = useRef<number>(undefined);
  const final = useRef<HTMLDivElement>(null);
  const turnoFinal = useRef<HTMLElement>(null);

  useEffect(() => {
    // Solo en una conversación vacía: al recargar o volver al servicio, su historial ya está recuperado.
    if (!inicio || !listo || inicioEnviado.current || estado.entradas.length > 0) return;
    inicioEnviado.current = true;
    void enviar({ tipo: "texto", texto: inicio });
  }, [inicio, listo, estado.entradas.length, enviar]);

  const huboResultado = !estado.enCurso && turnoResuelto(estado);
  useEffect(() => {
    if (!huboResultado) return;
    setResueltoVigente(true);
    const t = setTimeout(() => setResueltoVigente(false), RESUELTO_MS);
    return () => clearTimeout(t);
  }, [huboResultado, estado.entradas.length]);

  // RUTI lee en voz alta un resumen de cada respuesta nueva. Lo recuperado del historial no se lee.
  useEffect(() => {
    if (!listo || estado.enCurso) return;
    const claves = estado.entradas.flatMap((e, i) => (e.rol === "agente" && e.completo ? [e.turnoId ?? `i${i}`] : []));
    if (!leidos.current) {
      leidos.current = new Set(claves);
      return;
    }
    const ultimo = estado.entradas.at(-1);
    const clave = claves.at(-1);
    if (!clave || leidos.current.has(clave) || ultimo?.rol !== "agente") return;
    leidos.current.add(clave);
    if (leer) void decir(resumirTurno(ultimo));
  }, [listo, estado.enCurso, estado.entradas, leer, decir]);

  // Se lee desde el inicio de la respuesta: un formulario o resultado largo no debe aterrizar en su final.
  // Solo al abrir el turno o al llegar otra tarjeta; los deltas de texto no mueven lo que el usuario está leyendo.
  const entradaFinal = estado.entradas.at(-1);
  const tarjetasFinal = entradaFinal?.rol === "agente" ? entradaFinal.artifacts.length : 0;
  useEffect(() => {
    if (entradaFinal?.rol === "agente") turnoFinal.current?.scrollIntoView({ block: "start" });
    else final.current?.scrollIntoView({ block: "end" });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `entradaFinal` cambia con cada delta.
  }, [estado.entradas.length, tarjetasFinal]);

  const vista = useMemo(
    () => derivarRuti({ chat: estado, escribiendo, grabando: voz.grabando, resueltoVigente }),
    [estado, escribiendo, voz.grabando, resueltoVigente],
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
  const ultimo = estado.entradas.at(-1);
  const esperandoTexto = estado.enCurso && (ultimo?.rol !== "agente" || (!ultimo.texto && !ultimo.artifacts.length));
  // El primer envío solo pide el formulario: aún no se consulta nada.
  const yaRespondio = estado.entradas.some((e) => e.rol === "agente" && e.completo);
  const conResultado =
    !!pasos && ultimo?.rol === "agente" && ultimo.completo && ultimo.artifacts.some((a) => a.tipo === pasos.resultado);
  const paso = conResultado ? 2 : estado.enCurso && yaRespondio ? 1 : 0;

  // El dictado termina segundos después de empezar: se lee el estado vigente, no el del momento del toque.
  const alDictado = useRef<(dicho: string) => void>(() => undefined);
  alDictado.current = (dicho) => {
    if (!estado.enCurso && listo) void enviar({ tipo: "texto", texto: dicho });
    else setTexto(dicho);
  };
  const pulsado = useRef(0);
  const empezarDictado = () => void voz.iniciar((dicho) => alDictado.current(dicho));
  /** Toque: graba y corta sola al callarte (o con otro toque). Mantener presionado: corta al soltar. */
  const alPresionar = (e: PointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return;
    if (voz.grabando) {
      pulsado.current = 0;
      voz.detener();
      return;
    }
    pulsado.current = performance.now();
    empezarDictado();
  };
  const alSoltar = () => {
    if (pulsado.current && performance.now() - pulsado.current > MANTENER_MS) voz.detener();
    pulsado.current = 0;
  };
  // Teclado (Enter/Espacio llegan como clic sin puntero).
  const alClicTeclado = (e: MouseEvent<HTMLButtonElement>) => {
    if (e.detail !== 0) return;
    if (voz.grabando) voz.detener();
    else empezarDictado();
  };
  const estadoMic = voz.grabando
    ? "Escuchando: toca para enviar"
    : voz.preparando
      ? "Preparando el micrófono…"
      : voz.transcribiendo
        ? "Transcribiendo…"
        : "Hablar con RUTI";

  const reiniciar = () => {
    nueva();
    if (inicio) void enviar({ tipo: "texto", texto: inicio });
  };

  return (
    <div className="conversacion" data-icono={icono}>
      <aside className="conversacion__ruti">
        <Ruti vista={vista} encuadre="cabeza" hablando={voz.hablando} />
        <RutiStatus mensaje={voz.transcribiendo ? "Entendiendo lo que dijiste…" : vista.mensaje} />
      </aside>

      <div className="conversacion__principal">
        <div className="conversacion__cabeza">
          <Link to="/servicios" className="boton boton--icono" aria-label="Volver a servicios">
            <Icono nombre="atras" />
          </Link>
          <span className="conversacion__insignia" aria-hidden="true">
            <Icono nombre={icono} tamano={22} />
          </span>
          <div className="conversacion__titulos">
            <h1>{titulo}</h1>
            {descripcion && <p>{descripcion}</p>}
          </div>
          <button
            type="button"
            className="boton boton--icono"
            aria-pressed={leer}
            aria-label="RUTI lee un resumen de cada respuesta en voz alta"
            title={leer ? "Silenciar a RUTI" : "Activar la voz de RUTI"}
            onClick={() => voz.setLeer(!leer)}
          >
            <Icono nombre={leer ? "altavoz" : "silencio"} />
          </button>
          {estado.entradas.length > 0 && (
            <button type="button" className="boton boton--secundario boton--chico" onClick={reiniciar} disabled={estado.enCurso} aria-label={inicio ? "Nueva consulta" : "Nueva conversación"}>
              Nueva
              {inicio && <span className="solo-ancho"> consulta</span>}
            </button>
          )}
        </div>
        {pasos && (
          <ol className="pasador" aria-label="Progreso">
            {pasos.nombres.map((p, i) => (
              <li key={p} data-estado={i < paso || conResultado ? "hecho" : i === paso ? "actual" : undefined} aria-current={i === paso ? "step" : undefined}>
                <span className="pasador__num">{i < paso || conResultado ? <Icono nombre="check" tamano={14} /> : i + 1}</span>
                {p}
              </li>
            ))}
          </ol>
        )}
        {aviso}
        <div className="hilo" role="log" aria-live="polite" aria-label="Conversación con RUTI">
          {estado.entradas.length === 0 && (
            <div className="hilo__vacio">
              <span className="hilo__chispa" aria-hidden="true">
                <Icono nombre="chispa" tamano={28} />
              </span>
              <p>
                <strong>Pregúntame lo que necesites.</strong>
                <br />
                Escribe o toca el micrófono. También puedes empezar con una de estas:
              </p>
              {!inicio && (
                <ul className="sugerencias" aria-label="Sugerencias">
                  {SUGERENCIAS.map((t) => (
                    <li key={t.texto}>
                      <button type="button" className="sugerencia" disabled={!listo} onClick={() => void enviar({ tipo: "texto", texto: t.texto })}>
                        <span className="sugerencia__icono">
                          <Icono nombre={t.icono} tamano={20} />
                        </span>
                        {t.texto}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {estado.entradas.map((e, i) =>
            e.rol === "agente" ? (
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

        {voz.aviso && (
          <div className="banda banda--voz" role="status">
            <span>{voz.aviso}</span>
            <button type="button" className="boton boton--enlace" onClick={voz.cerrarAviso}>
              Entendido
            </button>
          </div>
        )}

        <form className="compositor" onSubmit={mandar}>
          {voz.microfonoDisponible && (
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
              onPointerDown={alPresionar}
              onPointerUp={alSoltar}
              onPointerCancel={alSoltar}
              onClick={alClicTeclado}
              onContextMenu={(e) => e.preventDefault()}
            >
              <Icono nombre={voz.grabando ? "detener" : "mic"} />
            </button>
          )}
          <label htmlFor="mensaje" className="sr-only">
            Escribe tu mensaje
          </label>
          <textarea
            id="mensaje"
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
                    : "Escribe o habla con RUTI…"
            }
            onChange={(e) => alEscribir(e.target.value)}
            onKeyDown={alTeclear}
          />
          <button className="boton boton--primario boton--fisico" disabled={estado.enCurso || !listo || !texto.trim()} aria-label="Enviar">
            <Icono nombre="flecha" />
          </button>
        </form>
      </div>
    </div>
  );
}
