import { useEffect, useState } from 'react'
import { subscribeStartup, type StartupState } from '../python/client'

/** Shows progress while Python starts in the browser, and explains a failure. */
export function StartupNotice() {
  const [startup, setStartup] = useState<StartupState | null>(null)
  useEffect(() => subscribeStartup(setStartup), [])

  if (!startup || startup.state === 'ready') return null
  if (startup.state === 'failed') {
    return (
      <div className="notice error">
        Boster kunde inte starta: {startup.message}. Kontrollera internetanslutningen och ladda om sidan. Boster behöver en
        modern webbläsare (Chrome, Edge, Firefox eller Safari).
      </div>
    )
  }
  return <div className="notice">{startup.message}</div>
}
