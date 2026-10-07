import { useEffect, useRef, useState, useCallback } from 'react'
import type { VehicleState } from '../protocol'

const URL = import.meta.env.VITE_AGENT_WS_URL || 'ws://localhost:8765'

// Connects to the on-device agent, exposes the latest state, a link flag, and a
// command sender. Auto-reconnects so a Pi reboot or agent restart self-heals.
export function useAgentSocket(enabled = true) {
  const [state, setState] = useState<VehicleState | null>(null)
  const [linked, setLinked] = useState(false)
  const ws = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!enabled) return
    let stopped = false
    let timer: number | undefined

    const connect = () => {
      if (stopped) return
      const sock = new WebSocket(URL)
      ws.current = sock
      sock.onopen = () => setLinked(true)
      sock.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg.type === 'state') setState(msg.state as VehicleState)
        } catch {
          /* ignore malformed frame */
        }
      }
      sock.onerror = () => sock.close()
      sock.onclose = () => {
        setLinked(false)
        timer = window.setTimeout(connect, 1500)
      }
    }

    connect()
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
      ws.current?.close()
    }
  }, [enabled])

  const send = useCallback((action: string, payload: Record<string, unknown> = {}) => {
    const sock = ws.current
    if (sock && sock.readyState === WebSocket.OPEN) {
      sock.send(JSON.stringify({ type: 'command', action, payload }))
    }
  }, [])

  return { state, linked, send }
}
