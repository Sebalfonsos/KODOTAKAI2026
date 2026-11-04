import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Ruti, RutiStatus } from "../../components/ruti/Ruti";
import { Icono, type NombreIcono } from "../../components/ui/Icono";
import { useConversacion } from "../../hooks/useConversacion";
import { derivarRuti, turnoResuelto } from "../../state/rutiMachine";
import type { TipoArtifact } from "../../services/chat";
import { VistaAgente } from "../agente/VistaAgente";
import { Compositor } from "./Compositor";
import { Hilo } from "./Hilo";

const RESUELTO_MS = 4000;
const CLAVE_MODO = "translogix.ayuda.modo";

function modoGuardado(): "chat" | "agente" {
  try {
    return sessionStorage.getItem(CLAVE_MODO) === "agente" ? "agente" : "chat";
  } catch {
    return "chat";
  }
}

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
  /** Muestra el switch Chat ⇄ Agente (solo en la ayuda general). */
  conAgente?: boolean;
}

export function Conversacion({ inicio, titulo, pasos, aviso, icono = "chat", descripcion, conAgente }: Props) {
  const conversacion = useConversacion(inicio ?? "ayuda");
  const { estado, listo, enviar, nueva, voz, escribiendo } = conversacion;
  const { leer } = voz;
  const inicioEnviado = useRef(false);
  const [resueltoVigente, setResueltoVigente] = useState(false);
  const [modo, setModoEstado] = useState(() => (conAgente ? modoGuardado() : "chat"));
  const agente = modo === "agente";
  const setModo = (m: "chat" | "agente") => {
    setModoEstado(m);
    try {
      sessionStorage.setItem(CLAVE_MODO, m);
    } catch {
      // Solo se pierde recordar el modo al recargar.
    }
  };

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

  const vista = useMemo(
    () => derivarRuti({ chat: estado, escribiendo, grabando: voz.grabando, resueltoVigente }),
    [estado, escribiendo, voz.grabando, resueltoVigente],
  );

  const contexto = { enviar, bloqueado: estado.enCurso || !listo };
  const ultimo = estado.entradas.at(-1);
  // El primer envío solo pide el formulario: aún no se consulta nada.
  const yaRespondio = estado.entradas.some((e) => e.rol === "agente" && e.completo);
  const conResultado =
    !!pasos && ultimo?.rol === "agente" && ultimo.completo && ultimo.artifacts.some((a) => a.tipo === pasos.resultado);
  const paso = conResultado ? 2 : estado.enCurso && yaRespondio ? 1 : 0;

  const reiniciar = () => {
    nueva();
    if (inicio) void enviar({ tipo: "texto", texto: inicio });
  };

  return (
    <div className="conversacion" data-icono={icono} data-modo={modo}>
      {!agente && (
        <aside className="conversacion__ruti">
          <Ruti vista={vista} encuadre="cabeza" hablando={voz.hablando} />
          <RutiStatus mensaje={voz.transcribiendo ? "Entendiendo lo que dijiste…" : vista.mensaje} />
        </aside>
      )}

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
          {conAgente && (
            <button type="button" role="switch" aria-checked={agente} className="switch" onClick={() => setModo(agente ? "chat" : "agente")}>
              <span data-activo={!agente || undefined}>Chat</span>
              <span data-activo={agente || undefined}>Agente</span>
              <span className="sr-only">: modo agente con voz</span>
            </button>
          )}
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
        {agente ? (
          <VistaAgente conversacion={conversacion} vista={vista} />
        ) : (
          <>
        <Hilo
          estado={estado}
          contexto={contexto}
          vacio={
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
          }
        />
        <Compositor conversacion={conversacion} idEntrada="mensaje" />
          </>
        )}
      </div>
    </div>
  );
}
