import { describe, expect, it } from "vitest";
import type { Artifact } from "../src/services/chat";
import { derivarRuti, type SenalesRuti } from "../src/state/rutiMachine";
import type { Escalamiento, TurnoAgente } from "../src/state/chatStore";

const turno = (tipo?: string): TurnoAgente => ({
  rol: "agente",
  turnoId: "t",
  artifacts: tipo ? [{ id: "a", tipo } as unknown as Artifact] : [],
  texto: "",
  citas: [],
  confianza: 0.9,
  completo: true,
});
const esc = (fase: Escalamiento["fase"]): Escalamiento => ({
  id: "e",
  criterio: "CRIT-002",
  prioridad: "alta",
  mensaje: "m",
  esperaS: 45,
  fase,
});
const senales = (cambios: Partial<SenalesRuti["chat"]> = {}, otras: Partial<SenalesRuti> = {}): SenalesRuti => ({
  chat: { entradas: [], enCurso: false, fallo: null, escalamiento: null, ...cambios },
  escribiendo: false,
  resueltoVigente: false,
  ...otras,
});

describe("derivarRuti", () => {
  it("empieza en reposo", () => {
    expect(derivarRuti(senales()).estado).toBe("reposo");
  });
  it("respeta la prioridad: escalamiento > error > pensando > resuelto > escuchando", () => {
    const todo = { fallo: { titulo: "x", reintentable: true }, enCurso: true, entradas: [turno()] };
    expect(derivarRuti(senales({ ...todo, escalamiento: esc("transfiriendo") })).estado).toBe("escalamiento");
    expect(derivarRuti(senales(todo)).estado).toBe("error");
    expect(derivarRuti(senales({ enCurso: true }, { escribiendo: true })).estado).toBe("pensando");
    expect(derivarRuti(senales({ entradas: [turno()] }, { resueltoVigente: true, escribiendo: true })).estado).toBe(
      "resuelto",
    );
    expect(derivarRuti(senales({}, { escribiendo: true })).estado).toBe("escuchando");
  });
  it("un formulario pendiente no cuenta como resuelto", () => {
    const s = senales({ entradas: [turno("formulario_cotizacion")] }, { resueltoVigente: true });
    expect(derivarRuti(s).estado).toBe("reposo");
  });
  it("no afirma que hay asesor hasta confirmarlo", () => {
    expect(derivarRuti(senales({ escalamiento: esc("transfiriendo") })).mensaje).not.toMatch(/ya está contigo/);
    expect(derivarRuti(senales({ escalamiento: esc("conectado") })).mensaje).toMatch(/ya está contigo/);
  });
  it("con el caso cerrado deja de mostrar escalamiento", () => {
    expect(derivarRuti(senales({ escalamiento: esc("resuelto") })).estado).toBe("reposo");
  });
});
