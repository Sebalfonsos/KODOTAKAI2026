import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";
import { mensajeError } from "../services/http";

/** Carga con estado de error y recarga. Si llega una respuesta vieja después de una nueva, se descarta. */
export function useDatos<T>(cargar: () => Promise<T>, deps: DependencyList, intervaloMs?: number) {
  const [datos, setDatos] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const turno = useRef(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- `cargar` cambia en cada render; mandan las `deps`.
  const recargar = useCallback(async () => {
    const mio = ++turno.current;
    setCargando(true);
    try {
      const d = await cargar();
      if (mio !== turno.current) return;
      setDatos(d);
      setError(null);
    } catch (e) {
      if (mio === turno.current) setError(mensajeError(e));
    } finally {
      if (mio === turno.current) setCargando(false);
    }
  }, deps);

  useEffect(() => {
    void recargar();
    if (!intervaloMs) return;
    const id = window.setInterval(() => void recargar(), intervaloMs);
    return () => window.clearInterval(id);
  }, [recargar, intervaloMs]);

  return { datos, error, cargando, recargar };
}
