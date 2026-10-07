import { useEffect, useState } from 'react'

// Live bed availability for verified hospitals, read from the central server's
// /hospitals endpoint (the hospital consoles write it there). Keyed by hospital
// id — the same ids the dashboard already uses (hospitals.ts / registry), so a
// verified hospital's beds line up with its destination option.
//
// The dashboard runs on a different port than the server, so this is a plain
// cross-origin GET (the server enables CORS for its read-only data endpoints).
// If the server is unreachable, beds are simply empty and the UI is unchanged.

export interface Beds {
  ed_open?: boolean
  beds_available?: number | null
  beds_total?: number | null
  icu_available?: number | null
  note?: string | null
  updated?: string | null
}

const SERVER =
  (import.meta as any).env?.VITE_SERVER_URL ||
  `${location.protocol}//${location.hostname}:4000`

export function useHospitalBeds(pollMs = 5000): Record<string, Beds> {
  const [beds, setBeds] = useState<Record<string, Beds>>({})
  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r = await fetch(`${SERVER}/hospitals`)
        const d = await r.json()
        if (!alive) return
        const m: Record<string, Beds> = {}
        for (const h of d.hospitals || []) if (h && h.id && h.beds) m[h.id] = h.beds
        setBeds(m)
      } catch {
        /* server not reachable — leave beds empty; picker behaves as before */
      }
    }
    load()
    const t = setInterval(load, pollMs)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [pollMs])
  return beds
}
