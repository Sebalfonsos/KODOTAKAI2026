import { Conversacion } from "../features/chat/Conversacion";

/** Cada servicio arranca un flujo del chat: el servidor emite el formulario y evalúa el escalamiento. */
export function Servicio({ inicio, titulo }: { inicio?: string; titulo: string }) {
  return <Conversacion key={inicio ?? "ayuda"} inicio={inicio} titulo={titulo} />;
}
