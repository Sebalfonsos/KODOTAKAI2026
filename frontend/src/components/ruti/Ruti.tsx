import { useLayoutEffect, useRef } from "react";
import svg from "../../assets/ruti/ruti.svg?raw";
import type { VistaRuti } from "../../state/rutiMachine";
import "./ruti.css";

export type Encuadre = "completo" | "cabeza";
const VIEWBOX: Record<Encuadre, string> = { completo: "0 0 1122 1402", cabeza: "100 0 940 780" };

interface Props {
  vista: Pick<VistaRuti, "estado" | "fase">;
  encuadre?: Encuadre;
  className?: string;
}

/**
 * SVG inline para controlar sus grupos. Usa IDs globales (`ojos`, `teal`…): solo una instancia por página.
 * Es decorativo: el estado se anuncia con `RutiStatus`. El contenido es un archivo propio del repo, no datos externos.
 */
export function Ruti({ vista, encuadre = "completo", className }: Props) {
  const contenedor = useRef<HTMLDivElement>(null);

  // Antes de pintar: el SVG viene guardado en `escuchando` y mostraría sus barras un instante.
  useLayoutEffect(() => {
    const raiz = contenedor.current?.querySelector("svg");
    if (!raiz) return;
    raiz.setAttribute("data-state", vista.estado);
    if (vista.fase) raiz.setAttribute("data-fase", vista.fase);
    else raiz.removeAttribute("data-fase");
    raiz.setAttribute("viewBox", VIEWBOX[encuadre]);
    raiz.removeAttribute("width");
    raiz.removeAttribute("height");
    raiz.removeAttribute("role");
    raiz.removeAttribute("aria-labelledby");
    raiz.setAttribute("aria-hidden", "true");
    raiz.setAttribute("focusable", "false");
  }, [vista.estado, vista.fase, encuadre]);

  return (
    <div
      ref={contenedor}
      className={`ruti ${className ?? ""}`}
      data-encuadre={encuadre}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

export function RutiStatus({ mensaje }: { mensaje: string }) {
  return (
    <p className="ruti-status" role="status" aria-live="polite">
      {mensaje}
    </p>
  );
}
