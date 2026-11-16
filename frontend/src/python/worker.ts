/// <reference lib="webworker" />
// Runs the Python app in a Web Worker, so analysing a PDF never freezes the page.
// The data directory (SQLite database and PDFs) is kept in the browser's IndexedDB.

import type { PyodideAPI } from 'pyodide'
import { DATA_DIRECTORY, PYODIDE_URL, startRuntime, type Runtime } from './runtime'
import type { FromWorker, ToWorker } from './messages'

// The backend's source files are bundled into this worker at build time.
const BACKEND_PREFIX = '../../../backend/'
const files = import.meta.glob(['../../../backend/app/**/*.py', '!**/pymupdf_text.py', '../../../backend/config/*.toml'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>
const sources = Object.fromEntries(Object.entries(files).map(([path, text]) => [path.slice(BACKEND_PREFIX.length), text]))

const post = (message: FromWorker, transfer: Transferable[] = []) => self.postMessage(message, transfer)

let py: PyodideAPI
let queue: Promise<unknown> = Promise.resolve()

function syncData(populate: boolean): Promise<void> {
  return new Promise((resolve, reject) => py.FS.syncfs(populate, (error: unknown) => (error ? reject(error) : resolve())))
}

async function start(): Promise<Runtime> {
  post({ type: 'progress', message: 'Laddar Python (första gången kan det ta en stund) …' })
  const { loadPyodide } = (await import(/* @vite-ignore */ `${PYODIDE_URL}pyodide.mjs`)) as typeof import('pyodide')
  py = await loadPyodide({ indexURL: PYODIDE_URL })
  py.FS.mkdirTree(DATA_DIRECTORY)
  py.FS.mount(py.FS.filesystems.IDBFS, {}, DATA_DIRECTORY)
  await syncData(true) // Load saved data from IndexedDB.
  const runtime = await startRuntime(py, sources, (message) => post({ type: 'progress', message }))
  await syncData(false)
  return runtime
}

const ready = start()
ready.then(
  () => post({ type: 'ready' }),
  (error) => post({ type: 'failed', message: String(error?.message ?? error) }),
)

self.onmessage = (event: MessageEvent<ToWorker>) => {
  const request = event.data
  // One request at a time: an import replaces the database, and must not interleave with other work.
  queue = queue.then(async () => {
    try {
      const runtime = await ready
      const response = await runtime.handle(request.method, request.path, request.headers, request.body)
      if (request.method !== 'GET') await syncData(false) // Save before reporting success.
      const body = response.body.slice().buffer
      post({ type: 'response', id: request.id, status: response.status, headers: response.headers, body }, [body])
    } catch (error) {
      post({ type: 'error', id: request.id, message: String((error as Error)?.message ?? error) })
    }
  })
}
