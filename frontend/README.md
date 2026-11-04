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

## Reglas

- El servidor decide cifras, veredictos y escalamientos; el front solo los muestra.
- El estado de RUTI se deriva en `src/state/rutiMachine.ts`, nunca de un temporizador que simule progreso.
- Solo una instancia del SVG de RUTI por página: usa IDs globales.
- Si un stream se corta, no se reenvía el mensaje: se reconcilia con el historial.
- Voz (`hooks/useVoz.ts`): el micrófono transcribe con `/voz/transcribir` y envía el texto al chat. RUTI lee en voz alta **un resumen** de cada respuesta (`state/resumenVoz.ts`), armado con los datos del artifact, no la respuesta completa. Si la voz falla, el chat sigue en texto.
