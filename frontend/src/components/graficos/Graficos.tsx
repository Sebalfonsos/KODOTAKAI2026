import { useEffect, useRef, useState, type PointerEvent } from "react";

/** Paleta validada con dataviz/validate_palette (claro, sobre #fff): ΔE CVD 31. Sigue a la serie, nunca a su posición. */
const COLORES = ["#2563eb", "#b45309"];
const numero = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 });

export interface FilaBarra {
  etiqueta: string;
  valor: number;
}

/** Barras horizontales de una serie: el texto es también la vista accesible, así que no hace falta tabla aparte. */
export function BarrasH({ filas, unidad, vacio = "Sin datos en este periodo." }: { filas: FilaBarra[]; unidad?: string; vacio?: string }) {
  if (!filas.length) return <p className="nota">{vacio}</p>;
  const max = Math.max(...filas.map((f) => f.valor), 1);
  return (
    <ul className="barras">
      {filas.map((f) => {
        const texto = `${numero.format(f.valor)}${unidad ? ` ${unidad}` : ""}`;
        return (
          <li key={f.etiqueta} title={`${f.etiqueta}: ${texto}`}>
            <span className="barras__etiqueta">{f.etiqueta}</span>
            <span className="barras__pista" aria-hidden="true">
              <span style={{ width: `${(f.valor / max) * 100}%` }} />
            </span>
            <span className="barras__valor">{texto}</span>
          </li>
        );
      })}
    </ul>
  );
}

export interface PuntoLinea {
  x: string;
  y: number;
  inf?: number;
  sup?: number;
}
export interface SerieLinea {
  nombre: string;
  puntos: PuntoLinea[];
  punteada?: boolean;
}

const ALTO = 280;
const M = { arriba: 16, derecha: 16, abajo: 28, izquierda: 44 };

/** Marcas "redondas" para el eje: 1, 2 o 5 × 10ⁿ. */
function pasoRedondo(max: number, marcas = 4) {
  const bruto = max / marcas;
  const base = 10 ** Math.floor(Math.log10(bruto || 1));
  const m = bruto / base;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * base;
}

const fechaEje = (iso: string) =>
  /^\d{4}-\d{2}-\d{2}/.test(iso) ? new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("es-CO", { day: "numeric", month: "short" }) : iso;

/** Línea en un solo eje, con banda de intervalo opcional, cruce y tooltip al pasar, y tabla como alternativa. */
export function GraficoLinea({ series, etiquetaX, unidad }: { series: SerieLinea[]; etiquetaX: string; unidad?: string }) {
  const caja = useRef<HTMLDivElement>(null);
  const [ancho, setAncho] = useState(640);
  const [activo, setActivo] = useState<number | null>(null);

  useEffect(() => {
    if (!caja.current || typeof ResizeObserver === "undefined") return;
    const o = new ResizeObserver(([e]) => setAncho(e.contentRect.width));
    o.observe(caja.current);
    return () => o.disconnect();
  }, []);

  const xs = [...new Set(series.flatMap((s) => s.puntos.map((p) => p.x)))].sort();
  const techo = Math.max(1, ...series.flatMap((s) => s.puntos.map((p) => p.sup ?? p.y)));
  const paso = pasoRedondo(techo);
  const yMax = Math.ceil(techo / paso) * paso;
  const anchoUtil = Math.max(ancho - M.izquierda - M.derecha, 10);
  const altoUtil = ALTO - M.arriba - M.abajo;
  const X = (x: string) => M.izquierda + (xs.indexOf(x) / Math.max(xs.length - 1, 1)) * anchoUtil;
  const Y = (y: number) => M.arriba + altoUtil - (y / yMax) * altoUtil;
  const marcas = Array.from({ length: Math.round(yMax / paso) + 1 }, (_, i) => i * paso);
  const cadaX = Math.max(1, Math.ceil(xs.length / Math.max(2, Math.floor(anchoUtil / 90))));

  const alMover = (e: PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left - M.izquierda) / anchoUtil) * (xs.length - 1));
    setActivo(Math.min(xs.length - 1, Math.max(0, i)));
  };
  const xActivo = activo === null ? null : xs[activo];
  const izquierdaTooltip = xActivo ? Math.min(X(xActivo) + 12, ancho - 190) : 0;

  return (
    <figure className="grafico">
      <ul className="grafico__leyenda">
        {series.map((s, i) => (
          <li key={s.nombre}>
            <svg width="24" height="8" aria-hidden="true">
              <line x1="0" y1="4" x2="24" y2="4" stroke={COLORES[i % COLORES.length]} strokeWidth="2" strokeDasharray={s.punteada ? "5 4" : undefined} />
            </svg>
            {s.nombre}
          </li>
        ))}
        {series.some((s) => s.puntos.some((p) => p.inf !== undefined)) && (
          <li>
            <span className="grafico__muestra-banda" aria-hidden="true" />
            Intervalo del 80 %
          </li>
        )}
      </ul>
      <div className="grafico__lienzo" ref={caja}>
        <svg
          width={ancho}
          height={ALTO}
          role="img"
          aria-label={`Gráfico de ${series.map((s) => s.nombre).join(" y ")}. Los valores están en la tabla de abajo.`}
          onPointerMove={alMover}
          onPointerLeave={() => setActivo(null)}
        >
          {marcas.map((m) => (
            <g key={m}>
              <line x1={M.izquierda} x2={ancho - M.derecha} y1={Y(m)} y2={Y(m)} className="grafico__rejilla" />
              <text x={M.izquierda - 8} y={Y(m) + 4} textAnchor="end" className="grafico__eje">
                {numero.format(m)}
              </text>
            </g>
          ))}
          {xs.map((x, i) =>
            i % cadaX === 0 ? (
              <text key={x} x={X(x)} y={ALTO - 8} textAnchor="middle" className="grafico__eje">
                {fechaEje(x)}
              </text>
            ) : null,
          )}
          {series.map((s, i) => {
            const banda = s.puntos.filter((p) => p.inf !== undefined && p.sup !== undefined);
            if (banda.length < 2) return null;
            const ida = banda.map((p) => `${X(p.x)},${Y(p.sup!)}`);
            const vuelta = [...banda].reverse().map((p) => `${X(p.x)},${Y(p.inf!)}`);
            return <polygon key={s.nombre} points={[...ida, ...vuelta].join(" ")} fill={COLORES[i % COLORES.length]} opacity={0.14} />;
          })}
          {series.map((s, i) => (
            <polyline
              key={s.nombre}
              points={s.puntos.map((p) => `${X(p.x)},${Y(p.y)}`).join(" ")}
              fill="none"
              stroke={COLORES[i % COLORES.length]}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={s.punteada ? "5 4" : undefined}
            />
          ))}
          {xActivo && (
            <g>
              <line x1={X(xActivo)} x2={X(xActivo)} y1={M.arriba} y2={M.arriba + altoUtil} className="grafico__cruce" />
              {series.map((s, i) => {
                const p = s.puntos.find((q) => q.x === xActivo);
                return p ? <circle key={s.nombre} cx={X(p.x)} cy={Y(p.y)} r={4} fill={COLORES[i % COLORES.length]} stroke="#fff" strokeWidth={2} /> : null;
              })}
            </g>
          )}
        </svg>
        {xActivo && (
          <div className="grafico__tooltip" style={{ left: izquierdaTooltip }}>
            <strong>{fechaEje(xActivo)}</strong>
            {series.map((s) => {
              const p = s.puntos.find((q) => q.x === xActivo);
              if (!p) return null;
              return (
                <span key={s.nombre}>
                  {s.nombre}: {numero.format(p.y)}
                  {unidad ? ` ${unidad}` : ""}
                  {p.inf !== undefined && p.sup !== undefined && ` (${numero.format(p.inf)}–${numero.format(p.sup)})`}
                </span>
              );
            })}
          </div>
        )}
      </div>
      <details className="grafico__tabla">
        <summary>Ver como tabla</summary>
        <div className="tabla-caja">
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">{etiquetaX}</th>
                <th scope="col">Serie</th>
                <th scope="col">Valor{unidad ? ` (${unidad})` : ""}</th>
                <th scope="col">Intervalo</th>
              </tr>
            </thead>
            <tbody>
              {series.flatMap((s) =>
                s.puntos.map((p) => (
                  <tr key={`${s.nombre}${p.x}`}>
                    <td>{fechaEje(p.x)}</td>
                    <td>{s.nombre}</td>
                    <td>{numero.format(p.y)}</td>
                    <td>{p.inf !== undefined && p.sup !== undefined ? `${numero.format(p.inf)}–${numero.format(p.sup)}` : "—"}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

export function RotuloSimulado() {
  return (
    <p className="rotulo-simulado" role="note">
      Datos simulados
    </p>
  );
}
