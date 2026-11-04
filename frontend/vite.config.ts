import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { VitePWA } from "vite-plugin-pwa";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode, command }) => {
  const objetivo = loadEnv(mode, ".", "VITE_").VITE_API_TARGET ?? "http://127.0.0.1:8100";
  // Solo en `npm run dev`: la cuenta demo sale del .env del backend (ignorado por Git). `npm run build` nunca la incluye.
  const raiz = loadEnv(mode, "..", "DEMO_CLIENTE_");
  const cuentaDemo =
    command === "serve" && mode === "development" && raiz.DEMO_CLIENTE_EMAIL && raiz.DEMO_CLIENTE_PASSWORD
      ? { email: raiz.DEMO_CLIENTE_EMAIL, password: raiz.DEMO_CLIENTE_PASSWORD }
      : null;
  return {
    define: { __CUENTA_DEMO__: JSON.stringify(cuentaDemo) },
    plugins: [
      react(),
      VitePWA({
        registerType: "autoUpdate",
        includeAssets: ["icons/icon-192.png", "icons/icon-512.png"],
        manifest: {
          name: "TransLogix · RUTI",
          short_name: "RUTI",
          description: "Consulta envíos, cotiza y resuelve dudas con RUTI, tu copiloto logístico.",
          lang: "es-CO",
          display: "standalone",
          start_url: "/",
          background_color: "#081B2F",
          theme_color: "#081B2F",
          icons: [
            { src: "icons/icon-192.png", sizes: "192x192", type: "image/png" },
            { src: "icons/icon-512.png", sizes: "512x512", type: "image/png" },
            { src: "icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
          ],
        },
        // Solo se cachea la app. Rastreos, cotizaciones y chat nunca salen de caché: serían datos viejos.
        workbox: { navigateFallbackDenylist: [/^\/api\//, /^\/health/] },
      }),
    ],
    server: {
      port: 5173,
      proxy: { "/api": { target: objetivo, changeOrigin: false }, "/health": { target: objetivo } },
    },
    test: { environment: "jsdom", include: ["tests/**/*.test.{ts,tsx}"], restoreMocks: true },
  };
});
