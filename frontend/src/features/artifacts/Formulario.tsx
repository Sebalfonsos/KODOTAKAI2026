import { useEffect, useId, useState, type FormEvent, type ReactNode } from "react";
import { Icono, type NombreIcono } from "../../components/ui/Icono";
import type { components } from "../../services/api";
import type { Accion } from "../../services/chat";
import { ErrorApi, json } from "../../services/http";
import type { PropsArtifact } from "./registro";

type Campo = components["schemas"]["CampoFormulario"];
type Valor = string | boolean;
type TipoFormulario = "formulario_cotizacion" | "formulario_guia" | "formulario_pqrs";

// Presentación por nombre de campo del contrato. Un campo nuevo sin entrada aquí se pinta igual, en "Otros datos".
const ICONO_CAMPO: Record<string, NombreIcono> = {
  guia: "codigo",
  origen: "pin",
  destino: "bandera",
  alto_cm: "regla",
  ancho_cm: "regla",
  largo_cm: "regla",
  peso_kg: "pesa",
  unidades: "cajas",
  valor_declarado_cop: "moneda",
  valor_reclamado_cop: "moneda",
  servicio: "camion",
  contenido: "caja",
  tipo: "documento",
  novedad: "alerta",
  descripcion: "chat",
};

const ICONO_OPCION: Record<string, NombreIcono> = {
  paqueteria: "caja",
  carga: "camion",
  cadena_frio: "copo",
  mercancia_peligrosa: "alerta",
  P: "chat",
  Q: "alerta",
  R: "documento",
  S: "escudo",
  averia_aparente: "caja",
  averia_oculta: "lupa",
  perdida: "pin",
};

interface Seccion {
  titulo: string;
  icono: NombreIcono;
  campos: string[];
  /** Clase de rejilla: medidas en 3 columnas, ruta en 2. */
  rejilla?: "dos" | "tres";
}

const SECCIONES: Partial<Record<TipoFormulario, Seccion[]>> = {
  formulario_cotizacion: [
    { titulo: "¿De dónde a dónde?", icono: "ruta", campos: ["origen", "destino"], rejilla: "dos" },
    { titulo: "Medidas del paquete", icono: "regla", campos: ["alto_cm", "ancho_cm", "largo_cm"], rejilla: "tres" },
    { titulo: "Peso y unidades", icono: "pesa", campos: ["peso_kg", "unidades"], rejilla: "dos" },
    { titulo: "Tu mercancía", icono: "caja", campos: ["servicio", "contenido", "valor_declarado_cop"] },
  ],
  formulario_pqrs: [
    { titulo: "Tu solicitud", icono: "documento", campos: ["tipo", "guia"] },
    { titulo: "Lo ocurrido", icono: "alerta", campos: ["novedad", "descripcion"] },
    { titulo: "Valor y soporte", icono: "moneda", campos: ["valor_reclamado_cop", "anotada_en_guia"] },
  ],
};

/** Trayecto desde un origen (`GET /trayectos/destinos`). */
interface Destino {
  valor: string;
  etiqueta: string;
  tiempo_entrega_horas: number;
}

const COP = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });

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

/** Agrupa los campos por sección; lo no listado va al final para no perder datos que pida el servidor. */
export function agrupar(tipo: TipoFormulario, campos: Campo[]): { seccion: Seccion | null; campos: Campo[] }[] {
  const secciones = SECCIONES[tipo];
  if (!secciones) return [{ seccion: null, campos }];
  const usados = new Set<string>();
  const grupos = secciones
    .map((s) => {
      const lista = s.campos.map((n) => campos.find((c) => c.nombre === n)).filter((c): c is Campo => !!c);
      lista.forEach((c) => usados.add(c.nombre));
      return { seccion: s, campos: lista };
    })
    .filter((g) => g.campos.length);
  const resto = campos.filter((c) => !usados.has(c.nombre));
  if (resto.length) grupos.push({ seccion: { titulo: "Otros datos", icono: "documento", campos: [] }, campos: resto });
  return grupos;
}

export function Formulario<T extends TipoFormulario>({ artifact: a, contexto }: PropsArtifact<T>) {
  const artifact = a as PropsArtifact<TipoFormulario>["artifact"];
  const base = useId();
  const [valores, setValores] = useState<Record<string, Valor>>(() =>
    Object.fromEntries(artifact.campos.map((c: Campo) => [c.nombre, valorInicial(c)])),
  );
  const [errores, setErrores] = useState<Record<string, string>>({});
  const accion = artifact.acciones.find((x: Accion) => x.tipo === "submit");
  // El formulario de guía es un solo campo: va en línea con su botón, como un buscador.
  const enLinea = artifact.tipo === "formulario_guia" && artifact.campos.length === 1;

  // Solo se ofrecen destinos con trayecto real desde el origen elegido. Si el catálogo falla, queda la lista
  // completa del formulario: el servidor valida igual al cotizar.
  const conRuta = artifact.campos.some((c: Campo) => c.nombre === "origen") && artifact.campos.some((c: Campo) => c.nombre === "destino");
  const origen = conRuta ? (valores.origen as string) : "";
  const [destinos, setDestinos] = useState<Destino[] | null>(null);
  useEffect(() => {
    setDestinos(null);
    if (!origen) return;
    const control = new AbortController();
    json<Destino[]>(`/api/v1/trayectos/destinos?origen=${encodeURIComponent(origen)}`, undefined, { signal: control.signal })
      .then((lista) => {
        setDestinos(lista);
        setValores((p) => (lista.some((d) => d.valor === p.destino) ? p : { ...p, destino: "" }));
      })
      .catch(() => undefined);
    return () => control.abort();
  }, [origen]);

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

  const pintarCampo = (c: Campo): ReactNode => {
    const id = `${base}-${c.nombre}`;
    const error = errores[c.nombre];
    const descritoPor = [c.ayuda && !c.ayuda.includes("/api/") && `${id}-ayuda`, error && `${id}-error`].filter(Boolean).join(" ") || undefined;
    const comun = {
      id,
      name: c.nombre,
      required: c.requerido !== false,
      "aria-invalid": error ? true : undefined,
      "aria-describedby": descritoPor,
    };
    const texto = valores[c.nombre] as string;
    const cambiar = (v: Valor) => setValores((p) => ({ ...p, [c.nombre]: v }));
    const icono = ICONO_CAMPO[c.nombre];
    const esDestino = conRuta && c.nombre === "destino";
    const opciones = esDestino && destinos ? destinos : (c.opciones ?? []);
    const horas = esDestino ? destinos?.find((d) => d.valor === texto)?.tiempo_entrega_horas : undefined;
    // El contrato trae aquí una nota técnica para el front ("GET /api/…"): no es para el usuario.
    const ayuda = c.ayuda?.includes("/api/") ? null : c.ayuda;
    const tarjetas = c.tipo === "seleccion" && opciones.length > 0 && opciones.length <= 4;

    const pie = (
      <>
        {ayuda && (
          <p className="campo__ayuda" id={`${id}-ayuda`}>
            {ayuda}
          </p>
        )}
        {esDestino && !origen && <p className="campo__ayuda">Primero elige la ciudad de origen.</p>}
        {horas !== undefined && (
          <p className="campo__ayuda campo__vista">
            <Icono nombre="reloj" tamano={14} /> Entrega estimada en {horas} h
          </p>
        )}
        {c.tipo === "moneda" && texto && Number.isFinite(Number(texto)) && (
          <p className="campo__ayuda campo__vista">{COP.format(Number(texto))}</p>
        )}
        {error && (
          <p className="campo__error" id={`${id}-error`}>
            <Icono nombre="alerta" tamano={16} />
            {error}
          </p>
        )}
      </>
    );

    if (tarjetas) {
      return (
        <fieldset className="campo campo--opciones" key={c.nombre} aria-describedby={descritoPor} aria-invalid={error ? true : undefined}>
          <legend>{c.etiqueta}</legend>
          <div className="opciones">
            {opciones.map((o) => (
              <label key={o.valor} className="opcion" data-elegida={texto === o.valor || undefined}>
                <input
                  type="radio"
                  className="sr-only"
                  name={`${id}-radio`}
                  value={o.valor}
                  checked={texto === o.valor}
                  required={c.requerido !== false}
                  onChange={() => cambiar(o.valor)}
                />
                <span className="opcion__icono">
                  <Icono nombre={ICONO_OPCION[o.valor] ?? "check"} tamano={22} />
                </span>
                <span className="opcion__texto">{o.etiqueta}</span>
              </label>
            ))}
          </div>
          {pie}
        </fieldset>
      );
    }

    if (c.tipo === "booleano") {
      return (
        <div className="campo campo--interruptor" key={c.nombre}>
          <label htmlFor={id} className="interruptor">
            <input
              {...comun}
              type="checkbox"
              role="switch"
              className="sr-only"
              checked={valores[c.nombre] === true}
              onChange={(e) => cambiar(e.target.checked)}
            />
            <span className="interruptor__pista" aria-hidden="true" />
            <span>{c.etiqueta}</span>
          </label>
          {pie}
        </div>
      );
    }

    return (
      <div className="campo" key={c.nombre} data-tipo={c.tipo} data-nombre={c.nombre}>
        <label htmlFor={id}>{c.etiqueta}</label>
        <div className="campo__control" data-con-icono={icono ? "" : undefined}>
          {icono && <Icono nombre={icono} tamano={18} className="campo__icono" />}
          {c.tipo === "seleccion" ? (
            <select {...comun} value={texto} disabled={esDestino && !origen} onChange={(e) => cambiar(e.target.value)}>
              <option value="">Selecciona…</option>
              {opciones.map((o) => (
                <option key={o.valor} value={o.valor}>
                  {o.etiqueta}
                </option>
              ))}
            </select>
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
              placeholder={c.patron?.includes("TLX") ? "TLX-000000-CO" : undefined}
              autoCapitalize={c.patron?.includes("TLX") ? "characters" : undefined}
              value={texto}
              onChange={(e) => cambiar(e.target.value)}
            />
          )}
          {c.unidad && <span className="campo__unidad">{c.unidad}</span>}
        </div>
        {pie}
      </div>
    );
  };

  const boton = accion && (
    <button className={`boton boton--${accion.estilo ?? "primario"} boton--grande`} disabled={contexto.bloqueado}>
      {accion.etiqueta}
      <Icono nombre="flecha" />
    </button>
  );

  if (enLinea) {
    return (
      <form className="formulario formulario--linea" onSubmit={alEnviar} noValidate>
        {pintarCampo(artifact.campos[0])}
        {boton}
      </form>
    );
  }

  return (
    <form className="formulario" onSubmit={alEnviar} noValidate>
      {agrupar(artifact.tipo, artifact.campos).map(({ seccion, campos }, i) =>
        seccion ? (
          <section className="formulario__seccion" key={seccion.titulo} aria-labelledby={`${base}-s${i}`}>
            <h3 id={`${base}-s${i}`}>
              <span className="formulario__num">{i + 1}</span>
              <Icono nombre={seccion.icono} tamano={18} />
              {seccion.titulo}
            </h3>
            <div className={`formulario__rejilla${seccion.rejilla ? ` formulario__rejilla--${seccion.rejilla}` : ""}`}>
              {campos.map(pintarCampo)}
            </div>
          </section>
        ) : (
          campos.map(pintarCampo)
        ),
      )}
      {boton}
    </form>
  );
}
