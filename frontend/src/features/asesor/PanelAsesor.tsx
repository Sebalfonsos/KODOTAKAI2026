import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Icono } from "../../components/ui/Icono";
import { useAuth } from "../../hooks/useAuth";
import { useDatos } from "../../hooks/useDatos";
import { tomar, verCola, type Escalamiento, type EstadoEscalamiento } from "../../services/asesor";
import { mensajeError } from "../../services/http";
import { Estado } from "../admin/comun";
import { ChatAsesor } from "./ChatAsesor";

// ponytail: el servidor no avisa cuando entra un caso nuevo; se consulta la cola. Con muchos asesores, un stream propio.
const REFRESCO_MS = 5000;
const PRIORIDAD: Record<number, { texto: string; clase: string }> = {
  1: { texto: "Urgente", clase: "error" },
  2: { texto: "Alta", clase: "error" },
  3: { texto: "Media", clase: "advertencia" },
  4: { texto: "Media", clase: "advertencia" },
  5: { texto: "Normal", clase: "" },
};
const PESTANAS: { estado: EstadoEscalamiento; texto: string }[] = [
  { estado: "pendiente", texto: "Pendientes" },
  { estado: "tomado", texto: "En atención" },
  { estado: "resuelto", texto: "Resueltos" },
];

function espera(s: number) {
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
}

function Caso({ caso, activo, alAbrir, alTomar, ocupado }: { caso: Escalamiento; activo: boolean; alAbrir: () => void; alTomar: () => void; ocupado: boolean }) {
  const p = PRIORIDAD[caso.prioridad] ?? PRIORIDAD[5];
  return (
    <li className="caso" data-activo={activo || undefined}>
      <button type="button" className="caso__abrir" onClick={alAbrir} aria-current={activo || undefined}>
        <span className="caso__fila">
          <span className={`etiqueta ${p.clase && `etiqueta--${p.clase}`}`}>{p.texto}</span>
          <span className="nota">
            <Icono nombre="reloj" tamano={14} /> {espera(caso.espera_s)}
          </span>
        </span>
        <strong>{caso.criterio_categoria}</strong>
        {caso.numero_guia && <span className="dato-mono">{caso.numero_guia}</span>}
        {caso.resumen_ia && <span className="caso__resumen">{caso.resumen_ia}</span>}
      </button>
      {caso.estado === "pendiente" && (
        <button type="button" className="boton boton--primario boton--chico caso__tomar" disabled={ocupado} onClick={alTomar}>
          Tomar
        </button>
      )}
    </li>
  );
}

export function PanelAsesor() {
  const { usuario } = useAuth();
  const [parametros, setParametros] = useSearchParams();
  const sesionId = parametros.get("sesion");
  const [pestana, setPestana] = useState<EstadoEscalamiento>("pendiente");
  const [ocupado, setOcupado] = useState(false);
  const [fallo, setFallo] = useState<string | null>(null);

  const pendientes = useDatos(() => verCola("pendiente"), [], REFRESCO_MS);
  const tomados = useDatos(() => verCola("tomado"), [], REFRESCO_MS);
  const resueltos = useDatos(() => (pestana === "resuelto" ? verCola("resuelto") : Promise.resolve(null)), [pestana]);
  const refrescar = () => {
    void pendientes.recargar();
    void tomados.recargar();
    void resueltos.recargar();
  };

  const abrir = (id: string | null) => setParametros(id ? { sesion: id } : {}, { replace: true });
  const tomarCaso = async (c: Escalamiento) => {
    setOcupado(true);
    setFallo(null);
    try {
      await tomar(c.id);
      setPestana("tomado");
      abrir(c.sesion_id);
    } catch (e) {
      setFallo(mensajeError(e)); // YA_TOMADO: otro asesor llegó primero.
    } finally {
      setOcupado(false);
      refrescar();
    }
  };

  const actual = pestana === "pendiente" ? pendientes : pestana === "tomado" ? tomados : resueltos;
  // Mis casos primero: el administrador ve también los de otros asesores.
  const lista = [...(actual.datos?.items ?? [])].sort((a, b) => Number(b.asesor_id === usuario?.id) - Number(a.asesor_id === usuario?.id));
  const conteo = { pendiente: pendientes.datos?.total, tomado: tomados.datos?.total, resuelto: undefined };

  return (
    <div className="consola" data-con-chat={sesionId ? "" : undefined}>
      <section className="consola__cola" aria-label="Cola de escalamientos">
        <h1>Cola de atención</h1>
        <div className="consola__pestanas" role="group" aria-label="Filtrar casos">
          {PESTANAS.map((p) => (
            <button key={p.estado} type="button" aria-pressed={pestana === p.estado} onClick={() => setPestana(p.estado)}>
              {p.texto}
              {conteo[p.estado] !== undefined && <span className="consola__conteo">{conteo[p.estado]}</span>}
            </button>
          ))}
        </div>
        {fallo && (
          <p className="alerta alerta--critica" role="alert">
            {fallo}
          </p>
        )}
        <Estado error={actual.error} cargando={actual.cargando} hayDatos={!!actual.datos} alReintentar={actual.recargar} />
        {actual.datos && !lista.length && (
          <p className="consola__vacio">{pestana === "pendiente" ? "No hay clientes esperando. Esta lista se actualiza sola." : "No hay casos aquí."}</p>
        )}
        <ul className="consola__lista">
          {lista.map((c) => (
            <Caso key={c.id} caso={c} activo={c.sesion_id === sesionId} ocupado={ocupado} alAbrir={() => abrir(c.sesion_id)} alTomar={() => void tomarCaso(c)} />
          ))}
        </ul>
      </section>
      {sesionId ? (
        <ChatAsesor key={sesionId} sesionId={sesionId} alCambiar={refrescar} alVolver={() => abrir(null)} />
      ) : (
        <div className="consola__sin-caso">
          <Icono nombre="asesor" tamano={32} />
          <p>
            <strong>Elige un caso de la cola.</strong>
            <br />
            Verás lo que el cliente habló con RUTI y podrás conversar con él en tiempo real.
          </p>
        </div>
      )}
    </div>
  );
}
