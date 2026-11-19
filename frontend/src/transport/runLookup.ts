// Public transport lookup: the page makes the HTTP calls the Python backend asks for and
// posts each raw response back. The backend decides what to ask, reads the answers and stores
// the result; it makes no network calls itself.

import { api, type ExternalRequest, type TransportInfo, type TransportStep } from '../api'

const KEY_STORAGE = 'boster.trafiklabKey'
const TIMEOUT_MS = 15_000
// The only services the page may call, whatever the backend asks for.
const ALLOWED_ORIGINS = new Set([
  'https://nominatim.openstreetmap.org',
  'https://api.resrobot.se',
  'https://valhalla1.openstreetmap.de',
])

/** The visitor's own Trafiklab key. It stays in this browser and is not part of an export. */
export function loadTrafiklabKey(): string | null {
  try {
    return localStorage.getItem(KEY_STORAGE)
  } catch {
    return null
  }
}

export function saveTrafiklabKey(key: string | null): void {
  try {
    if (key) localStorage.setItem(KEY_STORAGE, key)
    else localStorage.removeItem(KEY_STORAGE)
  } catch {
    // Storage blocked (e.g. a private window): the key then only lasts until the page is reloaded.
  }
}

export async function runTransportLookup(propertyId: number, key: string): Promise<TransportInfo> {
  let result = await api.transportStep(propertyId, { stage: 'start' })
  while (result.request) {
    result = await api.transportStep(propertyId, await call(result.request, key))
  }
  return result.transport
}

async function call(request: ExternalRequest, key: string): Promise<TransportStep> {
  const url = new URL(request.url)
  if (!ALLOWED_ORIGINS.has(url.origin) || request.method !== 'GET') {
    throw new Error(`Unexpected request to ${url.origin}`)
  }
  if (request.needs_key) url.searchParams.set('accessId', key)
  try {
    const response = await fetch(url, { credentials: 'omit', signal: AbortSignal.timeout(TIMEOUT_MS) })
    const text = await response.text()
    let body: unknown = text.slice(0, 2000) // Not JSON: only used to report the error.
    try {
      body = JSON.parse(text)
    } catch {
      // Keep the text.
    }
    return { stage: request.stage, status: response.status, body }
  } catch (error) {
    const timedOut = error instanceof DOMException && (error.name === 'TimeoutError' || error.name === 'AbortError')
    return { stage: request.stage, error: timedOut ? 'timeout' : 'network' }
  }
}
