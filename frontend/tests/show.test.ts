import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { correrShow, LINEA_TIEMPO, TOTAL_CASOS, VISTA_RESUMEN, vistaEn } from "../src/features/portada/show";
import { azar, distribuir, fracturar, trayectoria, type Poligono } from "../src/features/portada/vidrio";
import type { VistaShow } from "../src/features/portada/vista";

describe("línea de tiempo de la portada", () => {
  it("sigue el orden de estados del guion", () => {
    const estados = LINEA_TIEMPO.flatMap((e) => (e.estado ? [e.estado] : []));
    expect(estados).toEqual(["escuchando", "pensando", "escuchando", "error", "reposo", "escalamiento", "reposo", "resuelto", "reposo"]);
  });

  it("está ordenada en el tiempo", () => {
    const tiempos = LINEA_TIEMPO.map((e) => e.t);
    expect(tiempos).toEqual([...tiempos].sort((a, b) => a - b));
  });

  it("el camión llega, y al chocar desaparecen tarjetas, grietas y camión", () => {
    expect(vistaEn(14399)).toMatchObject({ camion: true, roto: false });
    expect(vistaEn(14399).casos).toHaveLength(TOTAL_CASOS);
    const roto = vistaEn(14400);
    expect(roto).toMatchObject({ camion: false, roto: true, grietas: 0, apagon: false, furia: false });
    expect(roto.casos).toEqual([]);
  });

  it("sigue pasando a un asesor lo que necesita una persona, en medio del vacío", () => {
    expect(vistaEn(21600)).toMatchObject({ estado: "escalamiento", escalamiento: "transfiriendo", roto: true });
  });

  it("la página se recompone antes del mensaje final", () => {
    expect(vistaEn(24900)).toMatchObject({ recomponiendo: true, roto: true, final: false });
    expect(vistaEn(26150)).toMatchObject({ recomponiendo: false, roto: false, final: true, estado: "resuelto" });
  });

  it("saltar lleva al estado final: nada roto y RUTI en calma", () => {
    const v = vistaEn(Infinity);
    expect(v).toEqual(vistaEn(31000));
    expect(v).toMatchObject({ fase: "calma", estado: "reposo", roto: false, camion: false, furia: false, temblor: 0, congelado: false, panel: false, final: false });
    expect(v.casos).toEqual([]);
  });

  it("el resumen de movimiento reducido no rompe nada y muestra todas las filas", () => {
    expect(VISTA_RESUMEN).toMatchObject({ roto: false, temblor: 0, casos: [] });
    expect(VISTA_RESUMEN.filas).toHaveLength(5);
    expect(VISTA_RESUMEN.filas.every((f) => f.lista)).toBe(true);
  });

  it("los destellos de pantalla completa están muy por debajo de 3 por segundo", () => {
    const destellos = LINEA_TIEMPO.filter((e) => e.destellos);
    expect(destellos.every((e, i) => i === 0 || e.t - destellos[i - 1].t > 1000)).toBe(true);
  });
});

describe("correrShow", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("emite la vista de cada momento y abortar la detiene", () => {
    const vistas: VistaShow[] = [];
    const control = new AbortController();
    correrShow({ al: (v) => vistas.push(v), signal: control.signal, raiz: () => null, impacto: { x: 0, y: 0 }, sonido: () => false });

    vi.advanceTimersByTime(3800);
    expect(vistas.at(-1)?.estado).toBe("pensando");
    expect(vistas.at(-1)?.casos).toHaveLength(8);

    const emitidas = vistas.length;
    control.abort();
    vi.advanceTimersByTime(40000);
    expect(vistas).toHaveLength(emitidas);
  });
});

function adentro(p: { x: number; y: number }, poligono: Poligono) {
  let dentro = false;
  for (let i = 0, j = poligono.length - 1; i < poligono.length; j = i++) {
    const a = poligono[i];
    const b = poligono[j];
    if (a.y > p.y !== b.y > p.y && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) dentro = !dentro;
  }
  return dentro;
}

describe("vidrio", () => {
  const casos = [
    { w: 1440, h: 900, impacto: { x: 720, y: 468 } },
    { w: 360, h: 740, impacto: { x: 180, y: 385 } },
    { w: 1024, h: 768, impacto: { x: 40, y: 700 } },
  ];

  it.each(casos)("los fragmentos cubren $w x $h sin huecos ni solapes", ({ w, h, impacto }) => {
    const piezas = fracturar(w, h, impacto, 11, 3);
    for (let x = 3; x < w; x += 37) {
      for (let y = 5; y < h; y += 41) {
        expect(piezas.filter((p) => adentro({ x, y }, p)).length).toBe(1);
      }
    }
  });

  it("es determinista con la misma semilla", () => {
    const [w, h, i] = [800, 600, { x: 400, y: 300 }];
    expect(fracturar(w, h, i, 9, 3, 5)).toEqual(fracturar(w, h, i, 9, 3, 5));
  });

  it("los fragmentos parten quietos, caen por gravedad y terminan invisibles", () => {
    const [pieza] = fracturar(800, 600, { x: 400, y: 300 }, 9, 3);
    const { frames } = trayectoria(pieza, { x: 400, y: 300 }, azar(3));
    const y = (f: Keyframe) => Number(/translate3d\([^,]+, (-?[\d.]+)px/.exec(String(f.transform))?.[1]);
    expect(y(frames[0])).toBe(0);
    expect(y(frames.at(-1)!)).toBeGreaterThan(y(frames[1]));
    expect(frames[0].opacity).toBe(1);
    expect(frames.at(-1)!.opacity).toBe(0);
  });

  it("las tarjetas quedan en pantalla y las primeras no le tapan la cara a RUTI", () => {
    const cabeza = { left: 900, top: 200, width: 400, height: 330 };
    const { ubicaciones } = distribuir(1440, 900, cabeza, TOTAL_CASOS);
    expect(ubicaciones).toHaveLength(TOTAL_CASOS);
    const centroX = cabeza.left + cabeza.width / 2;
    const centroY = cabeza.top + cabeza.height / 2;
    for (const u of ubicaciones.slice(0, 8)) {
      const sobreLaCara = Math.abs(u.x + 120 - centroX) < cabeza.width * 0.42 + 120 && Math.abs(u.y + 55 - centroY) < cabeza.height * 0.42 + 55;
      expect(sobreLaCara).toBe(false);
    }
    for (const u of ubicaciones) {
      expect(u.x).toBeGreaterThanOrEqual(8);
      expect(u.y).toBeGreaterThanOrEqual(8);
      expect(u.x).toBeLessThanOrEqual(1440);
      expect(u.y).toBeLessThanOrEqual(900);
    }
  });
});
