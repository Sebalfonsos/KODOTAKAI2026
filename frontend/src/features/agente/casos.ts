import type { NombreIcono } from "../../components/ui/Icono";

/** Casos de estudio del modo agente. Cada uno es un mensaje normal: lo resuelve el mismo orquestador del chat. */
export const CASOS: { titulo: string; dicho: string; icono: NombreIcono }[] = [
  { titulo: "Enviar carga sin clasificar", dicho: "Quiero enviar clavos de Bogotá a Medellín", icono: "caja" },
  { titulo: "Enviar con cadena de frío", dicho: "Necesito enviar vacunas de Bogotá a Medellín", icono: "copo" },
  { titulo: "Enviar mercancía peligrosa", dicho: "Quiero enviar 5 litros de ácido clorhídrico de Bogotá a Cali", icono: "alerta" },
  { titulo: "Envío prohibido", dicho: "Quiero enviar un perro a Medellín", icono: "escudo" },
  { titulo: "Rastrear una guía", dicho: "¿Dónde está la guía TLX-984021-CO?", icono: "camion" },
  { titulo: "Consultar cobertura", dicho: "¿Llegan a Quibdó?", icono: "ruta" },
  { titulo: "Reclamar por daño", dicho: "Me llegó la caja rota", icono: "documento" },
  { titulo: "Transferir a un asesor", dicho: "¿Qué pasa con la guía TLX-310482-CO?", icono: "asesor" },
];
