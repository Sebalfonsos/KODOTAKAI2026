import type { CSSProperties, Ref } from "react";
import { Ruti } from "../../components/ruti/Ruti";
import { Icono } from "../../components/ui/Icono";
import type { Escenario } from "./vidrio";
import type { FilaVista, VistaShow } from "./vista";
import "./caos.css";

const TONOS = ["#18c7c2", "#ffbd59", "#8fb8ff", "#c4b5fd", "#7ee2b8", "#f9a8a8", "#fde68a", "#8ff3ee"];

export function PanelRuti({ filas }: { filas: FilaVista[] }) {
  return (
    <div className="panel-ruti">
      <p className="panel-ruti__titulo">
        <Icono nombre="ruta" tamano={18} />
        Panel de RUTI
      </p>
      <ol>
        {filas.map((f) => (
          <li key={f.clave} data-lista={f.lista || undefined}>
            <span className="panel-ruti__clave">{f.clave}</span>
            <span className="panel-ruti__valor">
              {f.valor.split(" ").map((palabra, i) => (
                <span key={i} style={{ "--n": i } as CSSProperties}>
                  {palabra}{" "}
                </span>
              ))}
            </span>
            <Icono nombre="check" tamano={16} className="panel-ruti__check" />
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Lo que se rompe con la página: tarjetas y grietas viven dentro de ella para salir volando en los fragmentos. */
export function Avalancha({ vista, escenario }: { vista: VistaShow; escenario: Escenario | null }) {
  if (!escenario || vista.fase !== "activo") return null;
  return (
    <>
      <ul className="avalancha" aria-hidden="true">
        {vista.casos.map((c) => {
          const u = escenario.ubicaciones[c.id];
          return (
            <li
              key={c.id}
              className="caso"
              style={{ "--x": `${u.x}px`, "--y": `${u.y}px`, "--r": `${u.r}deg`, "--e": u.e, "--tono": TONOS[c.id % TONOS.length] } as CSSProperties}
            >
              <span className="caso__quien">
                <span className="caso__avatar">{c.iniciales}</span>
                {c.quien}
              </span>
              {c.texto}
            </li>
          );
        })}
      </ul>
      {vista.grietas > 0 && (
        <svg className="grietas" viewBox={`0 0 ${escenario.w} ${escenario.h}`} aria-hidden="true" focusable="false">
          {escenario.grietas.slice(0, vista.grietas).map((d) => (
            <g key={d}>
              <path className="grieta__sombra" d={d} pathLength={1} />
              <path className="grieta__luz" d={d} pathLength={1} />
            </g>
          ))}
        </svg>
      )}
    </>
  );
}

/** Camión de frente, en vectores simples. La placa es la guía por la que todos preguntaban. */
function Camion() {
  return (
    <div className="camion" aria-hidden="true">
      <svg viewBox="0 0 400 340" focusable="false">
        <rect x="46" y="4" width="308" height="132" rx="10" fill="#123b57" />
        <rect x="46" y="96" width="308" height="14" fill="#18c7c2" />
        <rect x="46" y="114" width="308" height="5" fill="#ffbd59" />
        <text x="200" y="66" textAnchor="middle" fontFamily="Inter, system-ui, sans-serif" fontWeight="800" fontSize="38" fill="#f5f8fc">
          TransLogix
        </text>
        <rect x="30" y="128" width="340" height="168" rx="20" fill="#0e7c7b" />
        <rect x="54" y="144" width="292" height="66" rx="10" fill="#081b2f" />
        <path d="M70 204 112 148h54l-42 56zM138 204l42-56h16l-42 56z" fill="#ffffff26" />
        <rect x="8" y="150" width="22" height="34" rx="5" fill="#081b2f" />
        <rect x="370" y="150" width="22" height="34" rx="5" fill="#081b2f" />
        <rect x="122" y="222" width="156" height="50" rx="6" fill="#081b2f" />
        <path d="M122 232h156M122 242h156M122 252h156M122 262h156" stroke="#18c7c2" strokeWidth="3" />
        <circle cx="78" cy="246" r="24" fill="#fff4cf" />
        <circle cx="322" cy="246" r="24" fill="#fff4cf" />
        <rect x="18" y="284" width="364" height="24" rx="8" fill="#b7c6d4" />
        <rect x="118" y="278" width="164" height="34" rx="4" fill="#ffbd59" stroke="#081b2f" strokeWidth="3" />
        <text x="200" y="302" textAnchor="middle" fontFamily="ui-monospace, monospace" fontWeight="800" fontSize="19" fill="#081b2f">
          TLX-000123-CO
        </text>
        <rect x="42" y="306" width="52" height="34" rx="6" fill="#050f1b" />
        <rect x="306" y="306" width="52" height="34" rx="6" fill="#050f1b" />
      </svg>
      <span className="camion__luz camion__luz--i" />
      <span className="camion__luz camion__luz--d" />
    </div>
  );
}

interface EscenaProps {
  vista: VistaShow;
  hablando: boolean;
  salida: Ref<HTMLButtonElement>;
  alSaltar: () => void;
}

/** Lo que no se rompe: el apagón, el camión, el vacío detrás del vidrio y la salida, siempre a mano. */
export function EscenaCaos({ vista, hablando, salida, alSaltar }: EscenaProps) {
  if (vista.fase !== "activo") return null;
  return (
    <div className="caos" data-tema="oscuro" data-roto={vista.roto || undefined}>
      {vista.apagon && <div className="caos__apagon" />}
      {vista.camion && <Camion />}
      {vista.roto && (
        <div className="vacio">
          {/* ponytail: segunda instancia del SVG con IDs repetidos; funciona porque ambas definen los mismos gradientes. */}
          <div className="vacio__ruti">
            <Ruti vista={{ estado: vista.estado, fase: vista.escalamiento }} encuadre="cabeza" hablando={hablando} />
          </div>
          {vista.panel && <PanelRuti filas={vista.filas} />}
        </div>
      )}
      {vista.destellos > 0 && <div key={vista.destellos} className="caos__destello" />}
      {vista.linea && !vista.final && (
        <p key={`${vista.linea}-${vista.golpes}`} className="caos__linea" data-grito={vista.grito || undefined} data-arriba={vista.camion || undefined} aria-hidden="true">
          {vista.linea}
        </p>
      )}
      <div className="caos__salida">
        <button ref={salida} type="button" className="caos__saltar" onClick={alSaltar}>
          Saltar
          <Icono nombre="flecha" tamano={18} />
        </button>
        <p>Demostración con datos de ejemplo</p>
      </div>
    </div>
  );
}
