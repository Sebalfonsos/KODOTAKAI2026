import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { correrShow, LINEA_TIEMPO, VISTA_RESUMEN, vistaEn, type VistaShow } from "../src/features/portada/show";

describe("línea de tiempo de la portada", () => {
  it("sigue el orden de estados del guion", () => {
    const estados = LINEA_TIEMPO.flatMap((e) => (e.estado ? [e.estado] : []));
    expect(estados).toEqual(["escuchando", "pensando", "reposo", "escalamiento", "resuelto", "reposo"]);
  });

  it("está ordenada en el tiempo", () => {
    const tiempos = LINEA_TIEMPO.map((e) => e.t);
    expect(tiempos).toEqual([...tiempos].sort((a, b) => a - b));
  });

  it("deja para el final el caso que necesita una persona", () => {
    const v = vistaEn(9500);
    expect(v.estado).toBe("escalamiento");
    expect(v.escalamiento).toBe("transfiriendo");
    expect(v.casos.filter((c) => !c.resuelto).map((c) => c.texto)).toEqual(["Quiero hablar con una persona."]);
  });

  it("saltar lleva al estado final: todo atendido y RUTI en calma", () => {
    const v = vistaEn(Infinity);
    expect(v).toEqual(vistaEn(17000));
    expect(v).toMatchObject({ fase: "calma", estado: "reposo", panel: false, final: false, celebrando: false });
    expect(v.casos.every((c) => c.resuelto)).toBe(true);
    expect(v.filas.every((f) => f.lista)).toBe(true);
  });

  it("el resumen de movimiento reducido no trae tarjetas y muestra todas las filas", () => {
    expect(VISTA_RESUMEN.casos).toEqual([]);
    expect(VISTA_RESUMEN.filas).toHaveLength(5);
    expect(VISTA_RESUMEN.filas.every((f) => f.lista)).toBe(true);
  });
});

describe("correrShow", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("emite la vista de cada momento y abortar la detiene", () => {
    const vistas: VistaShow[] = [];
    const control = new AbortController();
    correrShow({ al: (v) => vistas.push(v), signal: control.signal, sonido: () => false, alHablar: () => undefined });

    vi.advanceTimersByTime(4500);
    expect(vistas.at(-1)?.estado).toBe("pensando");
    expect(vistas.at(-1)?.casos).toHaveLength(8);

    const emitidas = vistas.length;
    control.abort();
    vi.advanceTimersByTime(20000);
    expect(vistas).toHaveLength(emitidas);
  });
});
