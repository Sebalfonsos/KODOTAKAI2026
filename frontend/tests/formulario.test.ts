import { describe, expect, it } from "vitest";
import { agrupar } from "../src/features/artifacts/Formulario";

const campo = (nombre: string) => ({ nombre, etiqueta: nombre, tipo: "texto" }) as Parameters<typeof agrupar>[1][number];

describe("agrupar", () => {
  it("ordena los campos por sección y omite las secciones vacías", () => {
    const g = agrupar("formulario_cotizacion", [campo("destino"), campo("origen"), campo("peso_kg")]);
    expect(g.map((x) => x.seccion?.titulo)).toEqual(["¿De dónde a dónde?", "Peso y unidades"]);
    expect(g[0].campos.map((c) => c.nombre)).toEqual(["origen", "destino"]);
  });

  it("no pierde un campo nuevo que el contrato agregue", () => {
    const g = agrupar("formulario_pqrs", [campo("tipo"), campo("campo_futuro")]);
    expect(g.at(-1)?.seccion?.titulo).toBe("Otros datos");
    expect(g.at(-1)?.campos.map((c) => c.nombre)).toEqual(["campo_futuro"]);
  });

  it("sin secciones definidas pinta todos los campos", () => {
    expect(agrupar("formulario_guia", [campo("guia")])).toEqual([{ seccion: null, campos: [campo("guia")] }]);
  });
});
