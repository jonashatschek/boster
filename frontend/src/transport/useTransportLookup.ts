// The public transport lookup for one apartment page: runs it automatically when needed, and
// lets the page retry, choose among offered addresses, or continue without transport.

import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type TransportInfo, type TransportStep } from '../api'
import { runTransportLookup, TRAFIKLAB_KEY } from './runLookup'

// Fetched automatically when there is no result yet, or the address has changed since.
const AUTOMATIC = new Set<TransportInfo['status']>(['not_fetched', 'stale', 'pending'])

export interface TransportLookup {
  busy: boolean
  error: string | null
  hasKey: boolean
  retry: () => void
  choose: (index: number) => void
  skip: () => void
}

export function useTransportLookup(
  propertyId: number,
  transport: TransportInfo | null, // Null while the apartment is loading.
  onChange: (transport: TransportInfo, propertyId: number) => void,
  // Called after the user chose an address, which also sets the apartment's municipality.
  onAddressChosen: () => void,
): TransportLookup {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Each apartment and address is fetched automatically at most once per visit, so a failure can't loop.
  const attempted = useRef(new Set<string>())

  async function run(first: TransportStep) {
    if (!TRAFIKLAB_KEY && first.stage !== 'skip') return
    setBusy(true)
    setError(null)
    try {
      const result =
        first.stage === 'skip'
          ? (await api.transportStep(propertyId, first)).transport
          : await runTransportLookup(propertyId, TRAFIKLAB_KEY!, first)
      onChange(result, propertyId)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Kollektivtrafiken kunde inte hämtas.')
    } finally {
      setBusy(false)
      // The choice saves the municipality first, so reload even if a later step failed.
      if (first.stage === 'choose') onAddressChosen()
    }
  }

  const autoQuery =
    TRAFIKLAB_KEY && transport && AUTOMATIC.has(transport.status) && transport.query
      ? `${propertyId}:${transport.query}`
      : null
  useEffect(() => {
    if (!autoQuery || busy || attempted.current.has(autoQuery)) return
    attempted.current.add(autoQuery)
    void run({ stage: 'start' })
    // run only depends on the property and the build-time key, which don't change here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoQuery, busy])

  return {
    busy,
    error,
    hasKey: Boolean(TRAFIKLAB_KEY),
    retry: () => void run({ stage: 'start' }),
    choose: (index) => void run({ stage: 'choose', choice: index }),
    skip: () => void run({ stage: 'skip' }),
  }
}
