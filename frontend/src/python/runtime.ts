// Starts Python (Pyodide) with the Boster app and passes API requests to it.
// Used by worker.ts; kept separate from the worker plumbing (IndexedDB, messages).

import type { PyodideAPI } from 'pyodide'

export const PYODIDE_VERSION = '314.0.8'
export const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`
// Pyodide ships the other packages the app needs (see backend/pyproject.toml).
const PYPI_PACKAGES = ['python-multipart==0.0.34']
const PYODIDE_PACKAGES = ['fastapi', 'sqlalchemy', 'pydantic', 'micropip']

const APP_ROOT = '/boster'
export const DATA_DIRECTORY = '/data'

export interface PythonResponse {
  status: number
  headers: [string, string][]
  body: Uint8Array
}

export interface Runtime {
  handle(method: string, path: string, headers: [string, string][], body: Uint8Array | null): Promise<PythonResponse>
}

/**
 * @param sources Python files keyed by their path below backend/, e.g. "app/main.py"
 *   and "config/risk_rules.toml".
 * @param onProgress Called with a Swedish description of each step.
 */
export async function startRuntime(
  py: PyodideAPI,
  sources: Record<string, string>,
  onProgress: (message: string) => void = () => {},
): Promise<Runtime> {
  onProgress('Laddar Python-paket …')
  await py.loadPackage(PYODIDE_PACKAGES)
  const micropip = py.pyimport('micropip')
  await micropip.install(PYPI_PACKAGES)
  micropip.destroy()

  onProgress('Startar Boster …')
  for (const [path, text] of Object.entries(sources)) {
    const target = `${APP_ROOT}/${path}`
    py.FS.mkdirTree(target.slice(0, target.lastIndexOf('/')))
    py.FS.writeFile(target, text)
  }
  py.FS.mkdirTree(DATA_DIRECTORY)

  const handleJs = await py.runPythonAsync(`
import sys
sys.path.insert(0, "${APP_ROOT}")
from pyodide.ffi import to_js
from app import browser

browser.boot("${DATA_DIRECTORY}", "${APP_ROOT}/config/risk_rules.toml")

async def handle_js(method, path, headers, body):
    status, response_headers, data = await browser.handle(
        method, path, headers.to_py(), body.to_bytes() if body is not None else b"")
    return to_js([status, response_headers, data])

handle_js
`)

  return {
    async handle(method, path, headers, body) {
      // undefined becomes None in Python (null would become JsNull).
      const result = await handleJs(method, path, headers, body ?? undefined)
      const [status, responseHeaders, data] = result as [number, [string, string][], Uint8Array]
      return { status, headers: responseHeaders, body: data }
    },
  }
}
