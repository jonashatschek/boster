// Public transport lookup: the page makes the HTTP calls the Python backend asks for and
// posts each raw response back. The backend decides what to ask, reads the answers and stores
// the result; it makes no network calls itself.

import { api, type ExternalRequest, type TransportInfo, type TransportStep } from '../api'

const TIMEOUT_MS = 15_000
// The only services the page may call, whatever the backend asks for.
const ALLOWED_ORIGINS = new Set([
  'https://nominatim.openstreetmap.org',
  'https://api.resrobot.se',
  'https://valhalla1.openstreetmap.de',
])

/**
 * The site's Trafiklab key, shared by all visitors. It is set when the site is built (a GitHub
 * Actions variable in CI, frontend/.env locally) and is readable by anyone in the built site;
 * it is not a secret. Null when the build has none.
 */
export const TRAFIKLAB_KEY: string | null = import.meta.env.VITE_TRAFIKLAB_API_KEY?.trim() || null

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
