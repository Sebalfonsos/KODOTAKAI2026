import { describe, expect, it } from "vitest";
import type { Artifact } from "../src/services/chat";
import { recortar, resumirTurno } from "../src/state/resumenVoz";
import { DetectorVoz, frases } from "../src/services/voz";

const turno = (texto: string, ...artifacts: object[]) => ({ texto, artifacts: artifacts as Artifact[] });

describe("resumirTurno", () => {
  it("resume la cotización con el total del servidor, no el texto completo", () => {
    const r = resumirTurno(
      turno("El envío Bogotá D.C. → Medellín cuesta $32.000 COP: flete $24.000, seguro $8.000. Peso facturable 15 kg.", {
        tipo: "resultado_cotizacion",
        origen: "Bogotá D.C.",
        destino: "Medellín",
        total: "32000.00",
        tiempo_estimado_horas: 24,
      }),
    );
    expect(r).toBe("El envío de Bogotá D.C. a Medellín cuesta 32.000 pesos y tarda unas 24 horas.");
  });

  it("en rastreo dice el estado y la llegada, y no omite una alerta crítica", () => {
    const r = resumirTurno(
      turno("", {
        tipo: "linea_tiempo_envio",
        estado_texto: "Tu envío va en camino.",
        eta: null,
        alerta: { nivel: "critica", mensaje: "Retenido en aduana." },
      }),
    );
    expect(r).toBe("Tu envío va en camino. Atención: Retenido en aduana.");
  });

  it("un formulario se resume con el texto del turno", () => {
    expect(resumirTurno(turno("Con gusto te cotizo. Completa los datos del envío.", { tipo: "formulario_cotizacion" }))).toBe(
      "Con gusto te cotizo. Completa los datos del envío.",
    );
    expect(resumirTurno(turno("", { tipo: "formulario_guia" }))).toBe("Completa los datos en pantalla para continuar.");
  });

  it("sin artifacts, lee como máximo dos frases cortas y sin Markdown", () => {
    const largo = "**Claro**, según el manual. Las baterías van protegidas. Además se etiquetan. Y algo más.";
    expect(resumirTurno(turno(largo))).toBe("Claro, según el manual. Las baterías van protegidas.");
    expect(recortar("palabra ".repeat(80)).length).toBeLessThanOrEqual(221);
  });

  it("el veredicto se lee sin el paréntesis técnico", () => {
    const r = resumirTurno(turno("", { tipo: "veredicto_mercancia", producto: "batería de litio suelta (9, ONU 3480)", veredicto: "restringido", documentos: ["a", "b", "c"] }));
    expect(r).toBe("Batería de litio suelta: se puede enviar con condiciones. Necesitas 3 documentos.");
  });

  it("dice la hora sin puntos que partan la frase", () => {
    const r = resumirTurno(turno("", { tipo: "linea_tiempo_envio", estado_texto: "En camino.", eta: "2026-11-03T21:00:00Z", alerta: null }));
    expect(r).toBe("En camino. Llegada estimada: martes, 3 de noviembre a las 4 de la tarde.");
  });
});

describe("frases", () => {
  it("corta por puntuación para sintetizar una a la vez", () => {
    expect(frases("Hola. ¿Cómo vas? Bien…")).toEqual(["Hola.", "¿Cómo vas?", "Bien…"]);
  });
});

describe("DetectorVoz", () => {
  /** Alimenta el detector con tramos de [rms, ms] en pasos de 50 ms y devuelve la última fase. */
  const correr = (d: DetectorVoz, tramos: [number, number][]) => {
    let fase = d.fase;
    for (const [rms, ms] of tramos) for (let t = 0; t < ms; t += 50) fase = d.muestra(rms, 50);
    return fase;
  };

  it("termina tras hablar y callar 1,3 s", () => {
    const d = new DetectorVoz();
    expect(correr(d, [[0.005, 300], [0.15, 1500], [0.005, 1000]])).toBe("hablando");
    expect(correr(d, [[0.005, 400]])).toBe("fin");
    expect(d.huboVoz).toBe(true);
  });

  it("descarta una grabación sin voz", () => {
    const d = new DetectorVoz();
    expect(correr(d, [[0.006, 8100]])).toBe("sin_voz");
    expect(d.huboVoz).toBe(false);
  });

  it("detecta la voz aunque el usuario hable desde el primer instante", () => {
    const d = new DetectorVoz();
    expect(correr(d, [[0.2, 2000]])).toBe("hablando");
  });

  it("un chasquido corto no cuenta como voz", () => {
    const d = new DetectorVoz();
    expect(correr(d, [[0.005, 300], [0.3, 100], [0.005, 2000]])).toBe("esperando");
  });
});
