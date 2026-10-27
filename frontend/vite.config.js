import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En dev local (npm run dev), on relaie /api vers l'API sur le port 8080.
// En conteneur, c'est Nginx qui s'en charge (voir nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
