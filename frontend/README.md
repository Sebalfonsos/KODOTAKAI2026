# Frontend TransLogix: PWA con RUTI

Plan y decisiones: `../docs/frontend/ESTRUCTURA_FRONT.md`. Contrato: `../docs/frontend.md` y `../docs/openapi.json`.

```bash
npm install
npm run dev        # http://localhost:5173; /api va por proxy a 127.0.0.1:8100
npm test           # pruebas unitarias
npm run typecheck
npm run build      # PWA en dist/
npm run gen:api    # regenera src/services/api.d.ts cuando cambie el contrato
```

Requiere el backend en marcha (ver `Makefile` en la raíz). Cambia el destino con `VITE_API_TARGET` (`.env.example`).

## Añadir un artifact

1. Crea el componente en `src/features/artifacts/`.
2. Reemplaza `Pendiente` por él en `registro.tsx`. Si el contrato añade un tipo, TypeScript exige registrarlo.

## Modo agente

Panel desplegable a la derecha (`src/features/agente/`), disponible en toda la app y con micrófono. Usa el mismo chat y la misma voz que los servicios (`hooks/useConversacion.ts`), en su propia sesión. Sus casos de estudio están en `casos.ts`; cada uno es un mensaje normal. No pinta a RUTI porque su SVG usa IDs globales y la página ya tiene uno.

## Consolas de trabajo

- **`/asesor`** (`src/features/asesor/`): cola de escalamientos, toma del caso y chat en vivo con el cliente. Para probarlo, usa una pestaña como cliente y otra como asesor: la sesión es por pestaña.
- **`/admin`** (`src/features/admin/`): indicadores, predicciones de ML con autoentrenamiento y simulador, chat administrativo, usuarios, conversaciones, envíos, PQRS, base de conocimiento y auditoría.
- Para que Predicciones tenga datos: `uv run python -m app.seed --historial-meses 12`. La API entrena los modelos sola al arrancar.

## Reglas

- El servidor decide cifras, veredictos y escalamientos; el front solo los muestra.
- El estado de RUTI se deriva en `src/state/rutiMachine.ts`, nunca de un temporizador que simule progreso.
- Solo una instancia del SVG de RUTI por página: usa IDs globales.
- Si un stream se corta, no se reenvía el mensaje: se reconcilia con el historial.
- Voz (`hooks/useVoz.ts`): el micrófono transcribe con `/voz/transcribir` y envía el texto al chat. RUTI lee en voz alta **un resumen** de cada respuesta (`state/resumenVoz.ts`), armado con los datos del artifact, no la respuesta completa. Si la voz falla, el chat sigue en texto.
