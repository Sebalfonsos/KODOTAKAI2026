import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Icono } from "../../components/ui/Icono";
import { useConversacion } from "../../hooks/useConversacion";
import { Compositor } from "../chat/Compositor";
import { Hilo } from "../chat/Hilo";
import { CASOS } from "./casos";

const CLAVE_ABIERTO = "translogix.agente.abierto";

function leerAbierto(): boolean {
  try {
    return sessionStorage.getItem(CLAVE_ABIERTO) === "1";
  } catch {
    return false;
  }
}

function Panel({ abierto, cerrar }: { abierto: boolean; cerrar: () => void }) {
  const conversacion = useConversacion("agente");
  const { estado, listo, enviar, nueva, voz } = conversacion;
  const { callar, detener } = voz;

  // Cerrar el panel corta el micrófono y la lectura: no se graba ni se habla con el panel oculto.
  useEffect(() => {
    if (abierto) return;
    detener();
    callar();
  }, [abierto, detener, callar]);

  return (
    // Sin Ruti: la página ya tiene el suyo y el SVG usa IDs globales (solo una instancia por página).
    <>
      <div className="agente__cabeza">
        <span className="hilo__chispa agente__chispa" aria-hidden="true">
          <Icono nombre="chispa" tamano={20} />
        </span>
        <div className="agente__titulos">
          <h2 id="agente-titulo">Modo agente</h2>
          <p>Dime qué necesitas y lo hacemos paso a paso.</p>
        </div>
        <button
          type="button"
          className="boton boton--icono"
          aria-pressed={voz.leer}
          aria-label="RUTI lee un resumen de cada respuesta en voz alta"
          title={voz.leer ? "Silenciar a RUTI" : "Activar la voz de RUTI"}
          onClick={() => voz.setLeer(!voz.leer)}
        >
          <Icono nombre={voz.leer ? "altavoz" : "silencio"} />
        </button>
        <button type="button" className="boton boton--icono" aria-label="Cerrar modo agente" onClick={cerrar}>
          <Icono nombre="x" />
        </button>
      </div>
      {estado.entradas.length > 0 && (
        <div className="agente__herramientas">
          <button type="button" className="boton boton--enlace" onClick={nueva} disabled={estado.enCurso}>
            Empezar otra tarea
          </button>
        </div>
      )}
      <Hilo
        estado={estado}
        contexto={{ enviar, bloqueado: estado.enCurso || !listo }}
        vacio={
          <div className="agente__vacio">
            <p>
              <strong>Toca el micrófono y dime qué quieres hacer.</strong>
              <br />
              Por ejemplo: «Quiero enviar clavos». Te doy los requisitos y el formulario.
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
        }
      />
      <Compositor conversacion={conversacion} idEntrada="mensaje-agente" />
    </>
  );
}

/** Herramienta del cliente: en las consolas de trabajo estorbaría sobre las tablas y el chat con el cliente. */
export function ModoAgente() {
  const { pathname } = useLocation();
  return /^\/(admin|asesor)(\/|$)/.test(pathname) ? null : <PanelDesplegable />;
}

/** Chat desplegable a la derecha, disponible en la aplicación del cliente. No es modal: la página sigue usable al lado. */
function PanelDesplegable() {
  const [abierto, setAbierto] = useState(leerAbierto);
  // La conversación se monta al primer uso y sigue viva al cerrar: reabrir no pierde la tarea en curso.
  const [usado, setUsado] = useState(abierto);
  const pestana = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);

  const cambiar = useCallback((valor: boolean) => {
    setAbierto(valor);
    if (valor) setUsado(true);
    try {
      sessionStorage.setItem(CLAVE_ABIERTO, valor ? "1" : "0");
    } catch {
      // Solo se pierde recordar el panel abierto al recargar.
    }
  }, []);

  const cerrar = useCallback(() => {
    cambiar(false);
    pestana.current?.focus();
  }, [cambiar]);

  // En escritorio el panel le hace sitio a la página en vez de taparla.
  useEffect(() => {
    document.documentElement.toggleAttribute("data-agente-abierto", abierto);
    return () => document.documentElement.removeAttribute("data-agente-abierto");
  }, [abierto]);

  useEffect(() => {
    if (abierto) panel.current?.querySelector("textarea")?.focus({ preventScroll: true });
  }, [abierto, usado]);

  // En el documento y no en el panel: el micrófono se deshabilita al transcribir y el foco se va al body.
  useEffect(() => {
    if (!abierto) return;
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === "Escape") cerrar();
    };
    document.addEventListener("keydown", alTeclear);
    return () => document.removeEventListener("keydown", alTeclear);
  }, [abierto, cerrar]);

  return (
    <>
      <button
        ref={pestana}
        type="button"
        className="agente-pestana"
        hidden={abierto}
        aria-expanded={abierto}
        aria-controls="modo-agente"
        onClick={() => cambiar(true)}
      >
        <Icono nombre="mic" tamano={20} />
        <span>Modo agente</span>
      </button>
      <aside
        ref={panel}
        id="modo-agente"
        className="agente"
        data-tema="claro"
        data-abierto={abierto || undefined}
        aria-labelledby="agente-titulo"
        inert={!abierto}
      >
        {usado && <Panel abierto={abierto} cerrar={cerrar} />}
      </aside>
    </>
  );
}
