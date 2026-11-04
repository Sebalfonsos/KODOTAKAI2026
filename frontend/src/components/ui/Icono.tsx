/** Una sola familia de íconos lineales (trazo 1.75, 24×24). Decorativos: el texto vecino da el significado. */
const TRAZOS = {
  caja: "M21 8 12 3 3 8v8l9 5 9-5V8ZM3 8l9 5 9-5M12 13v8M7.5 5.5l9 5",
  camion: "M3 6h11v10H3zM14 9h4l3 3v4h-7M7.5 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM17.5 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z",
  calculadora: "M6 3h12v18H6zM9 7h6M9 11h.01M12 11h.01M15 11h.01M9 14h.01M12 14h.01M15 14h.01M9 17h.01M12 17h.01M15 17h.01",
  alerta: "M12 3 2 20h20L12 3ZM12 10v4M12 17h.01",
  chat: "M4 5h16v11H9l-5 4V5ZM8.5 10.5h.01M12 10.5h.01M15.5 10.5h.01",
  pin: "M12 21s7-6.2 7-11.5a7 7 0 1 0-14 0C5 14.8 12 21 12 21ZM12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
  check: "M5 12.5 10 17l9-10",
  x: "M6 6l12 12M18 6 6 18",
  flecha: "M5 12h14M13 6l6 6-6 6",
  atras: "M19 12H5M11 6l-6 6 6 6",
  documento: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
  reloj: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5l3 2",
  escudo: "M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6l-7-3ZM9 12l2 2 4-4",
  copiar: "M9 9h11v11H9zM5 15H4V4h11v1",
  subir: "M12 16V4M7 9l5-5 5 5M4 20h16",
  asesor: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 21c0-4 3.6-6 8-6s8 2 8 6",
  mic: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3ZM5 11a7 7 0 0 0 14 0M12 18v3",
  detener: "M7 7h10v10H7z",
  altavoz: "M4 9h4l5-4v14l-5-4H4zM16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12",
  silencio: "M4 9h4l5-4v14l-5-4H4zM17 9l5 6M22 9l-5 6",
  codigo: "M3 7V4h3M18 4h3v3M21 17v3h-3M6 20H3v-3M7 8v8M10 8v8M13 8v8M16 8v8",
  bandera: "M5 21V4M5 4h11l-2 4 2 4H5",
  regla: "M3 17 17 3l4 4L7 21l-4-4ZM7 13l2 2M10 10l2 2M13 7l2 2",
  pesa: "M7 8h10l3 12H4L7 8ZM9 8a3 3 0 1 1 6 0",
  moneda: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM15 9.5c-.5-1-1.6-1.5-3-1.5-1.7 0-3 .8-3 2s1.3 1.7 3 2 3 .8 3 2-1.3 2-3 2c-1.4 0-2.5-.5-3-1.5M12 6.5v11",
  copo: "M12 2v20M4 7l16 10M20 7 4 17M9 4l3 2 3-2M9 20l3-2 3 2",
  cajas: "M3 12h8v8H3zM13 12h8v8h-8zM8 4h8v8H8z",
  lupa: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM20 20l-4-4",
  bodega: "M3 21V9l9-5 9 5v12M7 21v-8h10v8M7 17h10",
  ruta: "M6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM18 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM6 15V9a4 4 0 0 1 4-4h2M18 9v6a4 4 0 0 1-4 4h-2",
  chispa: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3ZM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z",
  estrella: "M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2-5.5-2.9-5.5 2.9 1-6.2L3 9.6l6.2-.9L12 3Z",
} as const;

export type NombreIcono = keyof typeof TRAZOS;

export function Icono({ nombre, tamano = 20, className }: { nombre: NombreIcono; tamano?: number; className?: string }) {
  return (
    <svg
      className={`icono ${className ?? ""}`}
      width={tamano}
      height={tamano}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={TRAZOS[nombre]} />
    </svg>
  );
}
