// The page's side of the Python worker: `pythonFetch` works like `fetch`, but the
// request is answered by the app running in this browser instead of a server.

import type { FromWorker, ToWorker } from './messages'

export type StartupState =
  | { state: 'starting'; message: string }
  | { state: 'ready' }
  | { state: 'failed'; message: string }

let startup: StartupState = { state: 'starting', message: 'Startar …' }
const listeners = new Set<(state: StartupState) => void>()
const pending = new Map<number, { resolve: (response: Response) => void; reject: (error: Error) => void }>()
let nextId = 1
let worker: Worker | null = null
let persistenceRequested = false

function setStartup(state: StartupState) {
  startup = state
  listeners.forEach((listener) => listener(state))
}

export function subscribeStartup(listener: (state: StartupState) => void): () => void {
  listeners.add(listener)
  listener(startup)
  return () => listeners.delete(listener)
}

function getWorker(): Worker {
  if (worker) return worker
  worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })
  worker.onmessage = (event: MessageEvent<FromWorker>) => {
    const message = event.data
    if (message.type === 'progress') setStartup({ state: 'starting', message: message.message })
    else if (message.type === 'ready') setStartup({ state: 'ready' })
    else if (message.type === 'failed') {
      setStartup({ state: 'failed', message: message.message })
    } else {
      const request = pending.get(message.id)
      if (!request) return
      pending.delete(message.id)
      if (message.type === 'error') request.reject(new Error(message.message))
      else {
        const body = message.status === 204 || message.status === 304 ? null : message.body
        request.resolve(new Response(body, { status: message.status, headers: message.headers }))
      }
    }
  }
  worker.onerror = (event) => setStartup({ state: 'failed', message: event.message || 'Okänt fel' })
  return worker
}

/** Start Python in the background as soon as the page loads. */
export function startPython() {
  getWorker()
}

export async function pythonFetch(path: string, init?: RequestInit): Promise<Response> {
  const request = new Request(new URL(path, location.href), init)
  const method = request.method.toUpperCase()
  const body = method === 'GET' || method === 'HEAD' ? null : new Uint8Array(await request.arrayBuffer())
  const headers = [...request.headers.entries()] as [string, string][]
  if (method !== 'GET') requestPersistentStorage()

  const id = nextId++
  const message: ToWorker = { id, method, path, headers, body }
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject })
    getWorker().postMessage(message, body ? [body.buffer] : [])
  })
}

/** Ask the browser not to clear the saved data when disk space runs low. */
function requestPersistentStorage() {
  if (persistenceRequested) return
  persistenceRequested = true
  navigator.storage?.persist?.().catch(() => {})
}
