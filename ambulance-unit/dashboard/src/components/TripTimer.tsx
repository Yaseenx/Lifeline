import { useEffect, useRef, useState } from 'react'

// Counts up while a trip is active; freezes the final duration when it ends.
export default function TripTimer({ active }: { active: boolean }) {
  const [elapsed, setElapsed] = useState(0)
  const startRef = useRef<number | null>(null)

  useEffect(() => {
    if (!active) {
      startRef.current = null
      return
    }
    startRef.current = Date.now()
    setElapsed(0)
    const id = window.setInterval(() => {
      if (startRef.current != null) {
        setElapsed(Math.floor((Date.now() - startRef.current) / 1000))
      }
    }, 1000)
    return () => clearInterval(id)
  }, [active])

  // Nothing to show until the first trip has started.
  if (!active && elapsed === 0) return null

  const mm = String(Math.floor(elapsed / 60)).padStart(2, '0')
  const ss = String(elapsed % 60).padStart(2, '0')

  return (
    <div className={`trip-timer ${active ? 'running' : 'stopped'}`}>
      <div className="tt-label">{active ? 'Trip time' : 'Trip ended'}</div>
      <div className="tt-time">
        {mm}:{ss}
      </div>
    </div>
  )
}
