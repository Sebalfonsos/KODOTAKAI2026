import type { ReactNode } from "react";

export const COP = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
export const NUM = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 });
const ZONA = "America/Bogota";
const FECHA_HORA = new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeStyle: "short", timeZone: ZONA });
const FECHA = new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeZone: ZONA });

export const fechaHora = (iso?: string | null) => (iso ? FECHA_HORA.format(new Date(iso)) : "—");
export const fecha = (iso?: string | null) => (iso ? FECHA.format(new Date(iso.length === 10 ? `${iso}T12:00:00-05:00` : iso)) : "—");

/** Fecha de hoy en Colombia en formato AAAA-MM-DD, desplazada `dias`. */
export function hoyMas(dias = 0) {
  const d = new Date(Date.now() + dias * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: ZONA }).format(d);
}

/** Muestra el error o la carga inicial; con datos ya pintados, una recarga no hace parpadear la vista. */
export function Estado({ error, cargando, hayDatos, alReintentar }: { error: string | null; cargando: boolean; hayDatos: boolean; alReintentar?: () => void }) {
  if (error) {
    return (
      <div className="alerta alerta--critica" role="alert">
        <span>{error}</span>
        {alReintentar && (
          <button type="button" className="boton boton--enlace" onClick={alReintentar}>
            Reintentar
          </button>
        )}
      </div>
    );
  }
  return cargando && !hayDatos ? <p role="status" className="nota">Cargando…</p> : null;
}

export function Paginador({ pagina, tamano, total, alCambiar }: { pagina: number; tamano: number; total: number; alCambiar: (p: number) => void }) {
  const paginas = Math.max(1, Math.ceil(total / tamano));
  return (
    <nav className="paginador" aria-label="Paginación">
      <span className="nota">
        {NUM.format(total)} {total === 1 ? "registro" : "registros"} · página {pagina} de {NUM.format(paginas)}
      </span>
      <button type="button" className="boton boton--secundario boton--chico" disabled={pagina <= 1} onClick={() => alCambiar(pagina - 1)}>
        Anterior
      </button>
      <button type="button" className="boton boton--secundario boton--chico" disabled={pagina >= paginas} onClick={() => alCambiar(pagina + 1)}>
        Siguiente
      </button>
    </nav>
  );
}

export function Seccion({ titulo, descripcion, acciones, children }: { titulo: string; descripcion?: ReactNode; acciones?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel-tarjeta">
      <div className="panel-tarjeta__cabeza">
        <div>
          <h2>{titulo}</h2>
          {descripcion && <p className="nota">{descripcion}</p>}
        </div>
        {acciones}
      </div>
      {children}
    </section>
  );
}

export function Filtro({ etiqueta, valor, opciones, alCambiar }: { etiqueta: string; valor: string; opciones: readonly (readonly [string, string])[]; alCambiar: (v: string) => void }) {
  return (
    <label className="filtro">
      <span>{etiqueta}</span>
      <select value={valor} onChange={(e) => alCambiar(e.target.value)}>
        {opciones.map(([v, t]) => (
          <option key={v} value={v}>
            {t}
          </option>
        ))}
      </select>
    </label>
  );
}
