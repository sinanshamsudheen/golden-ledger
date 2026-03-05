import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
    proxy: {
      "/auth": "http://localhost:8000",
      "/drive": "http://localhost:8000",
      // Only the real API sub-paths — NOT /documents or /documents/:id
      // which are React Router client-side routes.
      "^/documents/(latest|all|deals)(/.*)?$": {
        target: "http://localhost:8000",
        rewrite: (path) => path,
      },
      "/sync": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      react: path.resolve(__dirname, "./node_modules/react"),
      "react-dom": path.resolve(__dirname, "./node_modules/react-dom"),
    },
    dedupe: ["react", "react-dom", "react/jsx-runtime"],
  },
  optimizeDeps: {
    include: ["react", "react-dom", "framer-motion"],
  },
}));
