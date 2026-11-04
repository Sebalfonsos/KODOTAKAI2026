import { describe, expect, it } from "vitest";
import type { Artifact } from "../src/services/chat";
import { bitacora } from "../src/state/bitacora";
import type { TurnoAgente } from "../src/state/chatStore";

const base: TurnoAgente = { rol: "agente", turnoId: "t", artifacts: [], texto: "", citas: [], confianza: null, completo: true };
const textos = (t: Partial<TurnoAgente>) => bitacora({ ...base, ...t }).map((p) => p.texto);

describe("bitacora", () => {
  it("cuenta intención, etapas, artifacts y verificación en orden", () => {
    const artifact = { id: "a", tipo: "resultado_cotizacion" } as unknown as Artifact;
    expect(textos({ intencion: "cotizar", latencias: { total: 9, tool: 3, verify: 1 }, artifacts: [artifact] })).toEqual([
      "Entendí: cotizar un flete",
      "Consulté los datos del sistema",
      "Calculé la cotización",
      "Verifiqué la respuesta",
    ]);
  });

  it("la corrección del verificador reemplaza a 'verifiqué' y un turno abierto sigue trabajando", () => {
    const pasos = bitacora({ ...base, intencion: "x", corregido: true, latencias: { total: 1, verify: 1 }, completo: false });
    expect(pasos.map((p) => p.texto)).toEqual(["Entendí tu pregunta", "Corregí la respuesta tras verificarla", "Trabajando…"]);
    expect(pasos.at(-1)?.hecho).toBe(false);
  });
});
