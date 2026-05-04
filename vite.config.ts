import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const projectRoot = new URL(".", import.meta.url).pathname

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": projectRoot,
    },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom"],
          three: ["three"],
        },
      },
    },
  },
})
