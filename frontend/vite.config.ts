import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// A interface compilada vai para dentro do pacote Python e é servida pelo `orca`.
// Em desenvolvimento (`npm run dev`), os pedidos /api vão para o `orca` rodando na porta 8765.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../backend/orca/api/estatico",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8765", changeOrigin: true } },
  },
});
