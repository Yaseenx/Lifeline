import { useEffect, useRef, useState } from 'react'
import type { Hospital } from '../hospitals'
import { HOSPITALS, distanceKm } from '../hospitals'
import {
  FALLBACK_HOSPITALS,
  fetchHospitalsAround,
  fetchHospitalsGoogle,
  mergeHospitals,
} from '../hospitalsLive'

// Live nearest-hospitals list for the destination picker. Fetches every mapped
// hospital around the vehicle's GPS position (Overpass), merges with the
// curated verified list, and keeps distances fresh as the vehicle moves.
// Re-queries Overpass only when the vehicle has moved REFETCH_MOVE_KM from the
// last query centre, so the free service isn't hammered.

const REFETCH_MOVE_KM = 2.0

// Module-level cache: survives re-mounts, shared across panels.
let cache: { center: { lat: number; lng: number }; live: Hospital[] } | null = null

export function useNearbyHospitals(
  lat: number | undefined,
  lng: number | undefined,
  enabled: boolean,
) {
  const [hospitals, setHospitals] = useState<Hospital[]>(HOSPITALS)
  const [loading, setLoading] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const fetching = useRef(false)

  // Coarse position (~1 km grid) so the effect re-runs as the vehicle moves
  // without re-running on every GPS tick.
  const coarseLat = lat != null ? Math.round(lat * 100) / 100 : null
  const coarseLng = lng != null ? Math.round(lng * 100) / 100 : null

  useEffect(() => {
    if (!enabled || lat == null || lng == null || (!lat && !lng)) return
    const origin = { lat, lng }

    // Fresh enough: just re-sort with updated distances.
    if (cache && distanceKm(cache.center.lat, cache.center.lng, lat, lng) < REFETCH_MOVE_KM) {
      setHospitals(mergeHospitals(cache.live, origin))
      return
    }

    if (fetching.current) return
    fetching.current = true
    setLoading(true)
    // Source chain: Google Places (richest, like Google Maps' "hospitals near
    // me") -> OpenStreetMap Overpass -> static CMCHIS-empanelled fallback.
    ;(async () => {
      try {
        let live: Hospital[]
        let noteMsg: string | null = null
        try {
          live = await fetchHospitalsGoogle(lat, lng)
          if (!live.length) throw new Error('Google returned no hospitals')
        } catch (eg) {
          console.warn('[hospitals] Google Places unavailable:', eg instanceof Error ? eg.message : eg)
          live = await fetchHospitalsAround(lat, lng)
          noteMsg = live.length
            ? 'Using OpenStreetMap data (Google Places unavailable).'
            : 'No mapped hospitals nearby — showing verified list.'
        }
        cache = { center: origin, live }
        setHospitals(mergeHospitals(live, origin))
        setNote(noteMsg)
      } catch (e) {
        console.warn('[hospitals] live fetch failed:', e instanceof Error ? e.message : e)
        // Never leave "nearby" empty: last good live data if we have it,
        // plus the CMCHIS-empanelled fallback list.
        setHospitals(mergeHospitals([...(cache?.live ?? []), ...FALLBACK_HOSPITALS], origin))
        setNote('Live map lookup unavailable — showing CMCHIS-empanelled fallback list.')
      } finally {
        setLoading(false)
        fetching.current = false
      }
    })()
  }, [enabled, coarseLat, coarseLng]) // eslint-disable-line react-hooks/exhaustive-deps

  return { hospitals, loading, note }
}
