// Messages between the page (client.ts) and the Python worker (worker.ts).

export interface ToWorker {
  id: number
  method: string
  path: string
  headers: [string, string][]
  body: Uint8Array | null
}

export type FromWorker =
  | { type: 'progress'; message: string }
  | { type: 'ready' }
  | { type: 'failed'; message: string }
  | { type: 'response'; id: number; status: number; headers: [string, string][]; body: ArrayBuffer }
  | { type: 'error'; id: number; message: string }
