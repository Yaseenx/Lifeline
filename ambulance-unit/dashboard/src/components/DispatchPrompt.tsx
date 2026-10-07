import type { CSSProperties } from 'react'
import type { VehicleState } from '../protocol'

// Pop-up shown on the vehicle dashboard when the control centre dispatches this
// unit. The crew Accepts (starts the emergency trip -> hospital picker + corridor)
// or Declines (frees the unit for reassignment).

type Send = (action: string, payload?: Record<string, unknown>) => void

const overlay: CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,.55)',
  display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
  zIndex: 9999, paddingTop: '12vh',
}
const btn: CSSProperties = {
  flex: 1, padding: '12px 0', borderRadius: 10, border: 'none',
  fontSize: 15, fontWeight: 700, cursor: 'pointer',
}

export default function DispatchPrompt({ state, send }: { state: VehicleState | null; send: Send }) {
  const pd = state?.pending_dispatch
  if (!pd) return null
  const red = pd.priority === 'code_red'
  const card: CSSProperties = {
    width: 360, maxWidth: '90vw', background: '#0f1a26',
    border: `2px solid ${red ? '#e23b3b' : '#1f6fe0'}`, borderRadius: 16,
    padding: 20, color: '#eaf1f8', boxShadow: '0 20px 60px rgba(0,0,0,.5)',
    fontFamily: 'system-ui, sans-serif',
  }
  return (
    <div style={overlay}>
      <div style={card}>
        <div style={{ fontSize: 12, letterSpacing: 1, fontWeight: 700, color: red ? '#ff9ea1' : '#9db9ff' }}>
          NEW DISPATCH · {red ? 'CODE RED' : 'CODE BLUE'}
        </div>
        <div style={{ fontSize: 20, fontWeight: 700, margin: '6px 0', textTransform: 'capitalize' }}>
          {(pd.type || 'emergency').replace(/_/g, ' ')}
        </div>
        {pd.address ? <div style={{ color: '#9fb2c4', fontSize: 14 }}>{pd.address}</div> : null}
        <div style={{ color: '#7ee2a8', fontSize: 13, margin: '4px 0 16px' }}>
          📍 {Number(pd.lat).toFixed(4)}, {Number(pd.lng).toFixed(4)}
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button style={{ ...btn, background: '#1faa59', color: '#03110a' }}
                  onClick={() => send('accept_dispatch')}>Accept</button>
          <button style={{ ...btn, background: '#2a1416', color: '#ff9ea1', border: '1px solid #5b2327' }}
                  onClick={() => send('decline_dispatch')}>Decline</button>
        </div>
      </div>
    </div>
  )
}
