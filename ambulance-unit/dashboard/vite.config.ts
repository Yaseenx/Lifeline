import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// host:true so the dashboard is reachable on the Pi's kiosk browser / LAN.
export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173 },
})
