import { readPageText, type PageText } from './pdf/pageText'
import { pythonFetch } from './python/client'

// Typed client for the Boster backend. Types mirror backend/app/schemas.py.

export type VerificationStatus =
  | 'verified'
  | 'extracted'
  | 'user_entered'
  | 'calculated'
  | 'estimated'
  | 'missing'
  | 'conflicting'

export type ConcernLevel = 'low' | 'moderate' | 'high' | 'insufficient_information'

export interface SourceRef {
  observation_id: number
  value: number
  status: VerificationStatus
  method: string
  document_id: number | null
  document_name: string | null
  page: number | null
  printed_label: string | null
  note: string | null
}

export interface ReportedValue {
  value: number | null
  status: VerificationStatus
  sources: SourceRef[]
  note: string | null
}

export interface CalculatedValue {
  value: number | null
  formula: string
  inputs: Record<string, number>
  missing_inputs: string[]
  note: string | null
}

export interface YearValue {
  fiscal_year: number
  reported: ReportedValue | null
  calculated: CalculatedValue | null
  display_value: number | null
  display_status: VerificationStatus
  display_origin: 'reported' | 'calculated' | null
  warning: string | null
}

export interface MetricSeries {
  key: string
  label: string
  unit: string
  category: 'base_figure' | 'area' | 'key_figure'
  description: string
  area_basis: string | null
  values: YearValue[]
}

export interface RiskIndicator {
  key: string
  label: string
  value: number | null
  unit: string | null
  fiscal_year: number | null
  level: ConcernLevel
  level_label: string
  rationale: string
  rule: string
}

export interface RiskAssessment {
  fiscal_year: number | null
  overall_level: ConcernLevel
  overall_label: string
  overall_rule: string
  indicators: RiskIndicator[]
  disclaimer: string
}

export interface DocumentSummary {
  id: number
  cooperative_id: number | null
  original_filename: string
  document_url: string | null
  document_type: string
  reporting_year: number | null
  fiscal_period_start: string | null
  fiscal_period_end: string | null
  page_count: number
  extraction_status: 'succeeded' | 'partial' | 'needs_ocr' | 'failed'
  extraction_messages: string[]
  uploaded_at: string
}

export interface Finding {
  topic: string
  document_id: number
  document_name: string
  page: number
  excerpt: string
}

export interface CooperativeInfo {
  id: number
  name: string
  organisation_number: string | null
  land_tenure: 'owned' | 'leasehold' | null
  land_tenure_source: string | null
  created_at: string
  updated_at: string
}

export interface CooperativeOverview {
  cooperative: CooperativeInfo
  fiscal_years: number[]
  latest_fiscal_year: number | null
  metrics: MetricSeries[]
  risk: RiskAssessment
  completeness: { fiscal_year: number | null; available: string[]; missing: string[] }
  documents: DocumentSummary[]
  findings: Finding[]
}

export interface CooperativeListItem {
  id: number
  name: string
  organisation_number: string | null
  latest_fiscal_year: number | null
  document_count: number
  overall_level: ConcernLevel
  overall_label: string
  updated_at: string
}

export interface MetricDefinition {
  key: string
  label: string
  unit: string
  category: string
  description: string
  area_basis: string | null
}

export interface ComparedCooperative {
  id: number
  name: string
  organisation_number: string | null
  land_tenure: 'owned' | 'leasehold' | null
  fiscal_year: number | null
  period_months: number | null
  overall_level: ConcernLevel
  overall_label: string
  completeness_available: number
  completeness_total: number
}

export interface ComparisonCell {
  cooperative_id: number
  fiscal_year: number | null
  value: number | null
  status: VerificationStatus
  level: ConcernLevel | null
  level_label: string | null
  warning: string | null
  /** Why the value is missing, from the data; null when there is a value. */
  missing_reason: string | null
}

export interface HistoryPoint {
  fiscal_year: number
  value: number | null
  status: VerificationStatus
}

export interface ComparisonRow {
  key: string
  label: string
  unit: string
  description: string
  area_basis: string | null
  is_default: boolean
  cells: ComparisonCell[]
  history: Record<string, HistoryPoint[]>
  note: string | null
}

export interface CooperativeComparison {
  cooperatives: ComparedCooperative[]
  rows: ComparisonRow[]
  warnings: string[]
}

export const MAX_COMPARED_COOPERATIVES = 4

export const MAX_COMPARED_PROPERTIES = 4

export interface PropertyComparisonCell {
  property_id: number
  value: string | number | boolean | null
  status: VerificationStatus
  excerpt: string | null
  note: string | null
  level: ConcernLevel | null
  level_label: string | null
  fiscal_year: number | null
}

export interface PropertyComparisonRow {
  key: string
  group: string
  label: string
  kind: 'text' | 'number' | 'integer' | 'boolean' | 'date' | 'level' | 'findings'
  unit: string | null
  is_estimate: boolean
  note: string | null
  cells: PropertyComparisonCell[]
}

export interface ComparedProperty {
  id: number
  title: string | null
  address: string | null
  source_name: string | null
  cooperative_id: number | null
  cooperative_name: string | null
  fiscal_year: number | null
  overall_level: ConcernLevel | null
  overall_label: string | null
  maintenance: Finding[]
}

export interface PropertyComparison {
  properties: ComparedProperty[]
  rows: PropertyComparisonRow[]
  warnings: string[]
}

export type PropertyFieldValue = string | number | boolean | null

export interface PropertyField {
  key: string
  label: string
  value: PropertyFieldValue
  kind: 'text' | 'number' | 'integer' | 'boolean' | 'date' | 'longtext'
  unit: string | null
  status: VerificationStatus
  method: string | null
  excerpt: string | null
  note: string | null
}

export interface DerivedValue {
  key: string
  label: string
  value: number | null
  unit: string
  formula: string
  inputs: Record<string, string>
  missing_inputs: string[]
  note: string | null
}

export interface LinkedCooperative {
  id: number
  name: string
  organisation_number: string | null
  fiscal_year: number | null
  overall_level: ConcernLevel
  overall_label: string
  land_tenure: 'owned' | 'leasehold' | null
  indicators: RiskIndicator[]
  completeness_available: number
  completeness_total: number
}

export type TransportType = 'subway' | 'commuter_train' | 'bus'

export interface TransportStop {
  type: TransportType
  label: string
  status: VerificationStatus
  name: string | null
  walking_metres: number | null
  walking_seconds: number | null
  walk_text: string | null // "163 m (ca 2 min)", formatted by the backend; null without a walking distance.
  straight_metres: number | null
  note: string | null
}

export interface TransportInfo {
  status: 'not_fetched' | 'pending' | 'done' | 'failed' | 'stale' | 'choose' | 'skipped' | 'unavailable'
  message: string | null
  query: string | null
  looked_up_query: string | null
  place_label: string | null
  house_level: boolean | null
  retrieved_at: string | null
  source: string | null
  stops: TransportStop[]
  candidates: AddressCandidate[] // When status is 'choose'.
  truncated: boolean // There may be more hits than the candidates shown.
}

export interface AddressCandidate {
  label: string
  municipality: string
}

/** An HTTP call the backend asks the page to make (the Python code makes no network calls). */
export interface ExternalRequest {
  stage: 'geocode' | 'stops' | 'walking'
  service: 'nominatim' | 'resrobot' | 'valhalla'
  method: 'GET'
  url: string
  needs_key: boolean
}

export type TransportStep =
  | { stage: 'start' }
  | { stage: 'skip' }
  | { stage: 'choose'; choice: number }
  | { stage: ExternalRequest['stage']; status: number; body: unknown }
  | { stage: ExternalRequest['stage']; error: 'timeout' | 'network' }

export interface TransportStepResult {
  request: ExternalRequest | null
  transport: TransportInfo
}

export interface PropertyOverview {
  id: number
  title: string | null
  source_url: string | null
  source_name: string | null
  retrieval_status: 'fetched' | 'pasted' | 'fetch_failed' | 'manual'
  retrieval_message: string | null
  retrieved_at: string | null
  created_at: string
  updated_at: string
  fields: PropertyField[]
  description: PropertyField
  derived: DerivedValue[]
  cooperative: LinkedCooperative | null
  cooperative_suggestions: CooperativeListItem[]
  missing: string[]
  has_listing_text: boolean
  transport: TransportInfo
}

export interface PropertyListItem {
  id: number
  title: string | null
  address: string | null
  source_name: string | null
  asking_price: number | null
  living_area: number | null
  rooms: number | null
  monthly_fee: number | null
  cooperative_id: number | null
  cooperative_name: string | null
  cooperative_overall_level: ConcernLevel | null
  cooperative_overall_label: string | null
  retrieval_status: string
  updated_at: string
}

export class ApiError extends Error {}

async function send(path: string, init?: RequestInit): Promise<Response> {
  let response: Response
  try {
    response = await pythonFetch(path, init)
  } catch (caught) {
    console.error(caught)
    throw new ApiError('Något gick fel i webbläsaren. Ladda om sidan och försök igen.')
  }
  if (!response.ok) {
    let message = `Något gick fel (HTTP ${response.status}).`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = 'Ogiltig uppgift: ' + body.detail.map((d: { msg: string }) => d.msg).join(', ')
    } catch {
      // Keep the generic message.
    }
    throw new ApiError(message)
  }
  return response
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, init)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export const api = {
  listCooperatives: () => request<CooperativeListItem[]>('/api/cooperatives'),
  getCooperative: (id: number) => request<CooperativeOverview>(`/api/cooperatives/${id}`),
  updateCooperative: (id: number, changes: Partial<Pick<CooperativeInfo, 'name' | 'organisation_number' | 'land_tenure'>>) =>
    request<CooperativeOverview>(`/api/cooperatives/${id}`, json('PATCH', changes)),
  deleteCooperative: (id: number) => request<void>(`/api/cooperatives/${id}`, { method: 'DELETE' }),
  /** Every cooperative with its documents and values; apartments are kept, unlinked. */
  deleteAllCooperatives: () => request<void>('/api/cooperatives', { method: 'DELETE' }),
  addObservation: (id: number, observation: { metric_key: string; fiscal_year: number; value: number; note?: string }) =>
    request<CooperativeOverview>(`/api/cooperatives/${id}/observations`, json('POST', observation)),
  verifyObservation: (observationId: number) =>
    request<CooperativeOverview>(`/api/observations/${observationId}/verify`, { method: 'POST' }),
  deleteObservation: (observationId: number) =>
    request<CooperativeOverview>(`/api/observations/${observationId}`, { method: 'DELETE' }),
  /** `ids` is passed through as written in the URL, so the backend can report invalid ids. */
  compareCooperatives: (ids: string) =>
    request<CooperativeComparison>(`/api/comparisons/cooperatives?ids=${encodeURIComponent(ids)}`),
  /** `ids` is passed through as written in the URL, so the backend can report invalid ids. */
  compareProperties: (ids: string) =>
    request<PropertyComparison>(`/api/comparisons/properties?ids=${encodeURIComponent(ids)}`),
  listProperties: () => request<PropertyListItem[]>('/api/properties'),
  getProperty: (id: number) => request<PropertyOverview>(`/api/properties/${id}`),
  transportStep: (id: number, step: TransportStep) =>
    request<TransportStepResult>(`/api/properties/${id}/transport/step`, json('POST', step)),
  addPropertyFromText: (text: string, url?: string) =>
    request<PropertyOverview>('/api/properties/from-text', json('POST', { text, url: url || undefined })),
  addPropertyText: (id: number, text: string) =>
    request<PropertyOverview>(`/api/properties/${id}/text`, json('POST', { text })),
  updateProperty: (id: number, changes: Record<string, PropertyFieldValue>) =>
    request<PropertyOverview>(`/api/properties/${id}`, json('PATCH', changes)),
  verifyPropertyField: (id: number, field: string) =>
    request<PropertyOverview>(`/api/properties/${id}/fields/${field}/verify`, { method: 'POST' }),
  linkPropertyCooperative: (id: number, cooperativeId: number | null) =>
    request<PropertyOverview>(`/api/properties/${id}/cooperative`, json('PUT', { cooperative_id: cooperativeId })),
  deleteProperty: (id: number) => request<void>(`/api/properties/${id}`, { method: 'DELETE' }),
  deleteAllProperties: () => request<void>('/api/properties', { method: 'DELETE' }),
  listMetrics: () => request<MetricDefinition[]>('/api/metrics'),
  uploadDocument: async (file: File) => {
    let pages: PageText[] | null = null
    try {
      pages = await readPageText(await file.arrayBuffer())
    } catch {
      // Damaged or encrypted: the file is stored, and the document is reported as unreadable.
    }
    const form = new FormData()
    form.append('file', file)
    form.append('pages', JSON.stringify(pages))
    return request<DocumentSummary>('/api/documents/upload', { method: 'POST', body: form })
  },
  moveDocument: (documentId: number, cooperativeId: number) =>
    request<DocumentSummary>(`/api/documents/${documentId}`, json('PATCH', { cooperative_id: cooperativeId })),
  deleteDocument: (documentId: number) => request<void>(`/api/documents/${documentId}`, { method: 'DELETE' }),
  /** The stored PDF as a link the browser can open (an object URL for this tab only). */
  documentFileUrl: async (documentId: number) => {
    const response = await send(`/api/documents/${documentId}/file`)
    return URL.createObjectURL(new Blob([await response.arrayBuffer()], { type: 'application/pdf' }))
  },
  /** All data as a zip file. */
  exportData: async () => (await send('/api/backup')).blob(),
  /** Replace all data with an exported zip file. */
  importData: (file: File) =>
    request<void>('/api/backup', { method: 'POST', headers: { 'Content-Type': 'application/zip' }, body: file }),
}
