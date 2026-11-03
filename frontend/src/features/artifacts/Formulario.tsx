import { useId, useState, type FormEvent } from "react";
import type { components } from "../../services/api";
import type { Accion } from "../../services/chat";
import { ErrorApi } from "../../services/http";
import type { PropsArtifact } from "./registro";

type Campo = components["schemas"]["CampoFormulario"];
type Valor = string | boolean;

function valorInicial(c: Campo): Valor {
  if (c.tipo === "booleano") return c.valor === true;
  return c.valor === undefined || c.valor === null ? "" : String(c.valor);
}

/** Convierte al formato del contrato; el servidor valida de nuevo y es quien manda. */
function normalizar(campos: Campo[], valores: Record<string, Valor>) {
  const salida: Record<string, unknown> = {};
  for (const c of campos) {
    const v = valores[c.nombre];
    if (v === "" || v === undefined) continue;
    salida[c.nombre] = c.patron?.includes("TLX") && typeof v === "string" ? v.trim().toUpperCase() : v;
  }
  return salida;
}

type TipoFormulario = "formulario_cotizacion" | "formulario_guia" | "formulario_pqrs";

export function Formulario<T extends TipoFormulario>({ artifact: a, contexto }: PropsArtifact<T>) {
  const artifact = a as PropsArtifact<TipoFormulario>["artifact"];
  const base = useId();
  const [valores, setValores] = useState<Record<string, Valor>>(() =>
    Object.fromEntries(artifact.campos.map((c: Campo) => [c.nombre, valorInicial(c)])),
  );
  const [errores, setErrores] = useState<Record<string, string>>({});
  const accion = artifact.acciones.find((a: Accion) => a.tipo === "submit");

  const alEnviar = async (e: FormEvent) => {
    e.preventDefault();
    setErrores({});
    try {
      await contexto.enviar(
        { tipo: "artifact_submit", artifact_id: artifact.id, valores: normalizar(artifact.campos, valores) },
        accion?.endpoint ?? undefined,
      );
    } catch (err) {
      if (err instanceof ErrorApi && err.problema.errores) {
        setErrores(Object.fromEntries(err.problema.errores.map((x) => [x.campo, x.mensaje])));
      }
    }
  };

  return (
    <form className="formulario" onSubmit={alEnviar} noValidate>
      {artifact.campos.map((c: Campo) => {
        const id = `${base}-${c.nombre}`;
        const error = errores[c.nombre];
        const descritoPor = [c.ayuda && `${id}-ayuda`, error && `${id}-error`].filter(Boolean).join(" ") || undefined;
        const comun = {
          id,
          name: c.nombre,
          required: c.requerido !== false,
          "aria-invalid": error ? true : undefined,
          "aria-describedby": descritoPor,
        };
        const texto = valores[c.nombre] as string;
        const cambiar = (v: Valor) => setValores((p) => ({ ...p, [c.nombre]: v }));
        return (
          <div className="campo" key={c.nombre} data-tipo={c.tipo}>
            <label htmlFor={id}>{c.etiqueta}</label>
            <div className="campo__control">
              {c.tipo === "seleccion" ? (
                <select {...comun} value={texto} onChange={(e) => cambiar(e.target.value)}>
                  <option value="">Selecciona…</option>
                  {(c.opciones ?? []).map((o) => (
                    <option key={o.valor} value={o.valor}>
                      {o.etiqueta}
                    </option>
                  ))}
                </select>
              ) : c.tipo === "booleano" ? (
                <input
                  {...comun}
                  type="checkbox"
                  checked={valores[c.nombre] === true}
                  onChange={(e) => cambiar(e.target.checked)}
                />
              ) : c.tipo === "texto" && Number(c.max) > 200 ? (
                <textarea {...comun} value={texto} rows={3} onChange={(e) => cambiar(e.target.value)} />
              ) : (
                <input
                  {...comun}
                  type={c.tipo === "numero" ? "number" : c.tipo === "fecha" ? "date" : "text"}
                  inputMode={c.tipo === "numero" ? "decimal" : c.tipo === "moneda" ? "numeric" : undefined}
                  step={c.tipo === "numero" ? "any" : undefined}
                  min={c.min ?? undefined}
                  max={c.max ?? undefined}
                  pattern={c.patron ?? undefined}
                  autoCapitalize={c.patron?.includes("TLX") ? "characters" : undefined}
                  value={texto}
                  onChange={(e) => cambiar(e.target.value)}
                />
              )}
              {c.unidad && <span className="campo__unidad">{c.unidad}</span>}
            </div>
            {c.ayuda && (
              <p className="campo__ayuda" id={`${id}-ayuda`}>
                {c.ayuda}
              </p>
            )}
            {error && (
              <p className="campo__error" id={`${id}-error`}>
                {error}
              </p>
            )}
          </div>
        );
      })}
      {accion && (
        <button className={`boton boton--${accion.estilo ?? "primario"}`} disabled={contexto.bloqueado}>
          {accion.etiqueta}
        </button>
      )}
    </form>
  );
}
