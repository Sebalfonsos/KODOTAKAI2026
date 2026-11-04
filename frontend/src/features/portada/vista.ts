import type { FaseEscalamiento } from "../../state/chatStore";
import type { EstadoRuti } from "../../state/rutiMachine";

// Sin dependencias pesadas: la portada lo importa de entrada; el motor del show (`show.ts`) se carga aparte.

export type FaseShow = "reposo" | "activo" | "calma" | "resumen";

export interface CasoVista {
  id: number;
  quien: string;
  iniciales: string;
  texto: string;
}

export interface FilaVista {
  clave: string;
  valor: string;
  lista: boolean;
}

export interface VistaShow {
  fase: FaseShow;
  estado: EstadoRuti;
  escalamiento: FaseEscalamiento | null;
  linea: string;
  /** La línea ocupa la pantalla. */
  grito: boolean;
  final: boolean;
  hablando: boolean;
  panel: boolean;
  celebrando: boolean;
  temblor: 0 | 1 | 2 | 3;
  furia: boolean;
  congelado: boolean;
  apagon: boolean;
  camion: boolean;
  roto: boolean;
  recomponiendo: boolean;
  /** Contadores: cada aumento dispara una vez su efecto. */
  golpes: number;
  grietas: number;
  destellos: number;
  casos: CasoVista[];
  filas: FilaVista[];
}

export const VISTA_REPOSO: VistaShow = {
  fase: "reposo",
  estado: "reposo",
  escalamiento: null,
  linea: "¡Hola! Soy RUTI, tu copiloto logístico.",
  grito: false,
  final: false,
  hablando: false,
  panel: false,
  celebrando: false,
  temblor: 0,
  furia: false,
  congelado: false,
  apagon: false,
  camion: false,
  roto: false,
  recomponiendo: false,
  golpes: 0,
  grietas: 0,
  destellos: 0,
  casos: [],
  filas: [],
};
