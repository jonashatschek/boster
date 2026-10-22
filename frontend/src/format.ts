// Swedish formatting of numbers, statuses and labels.

import type { ConcernLevel, VerificationStatus } from './api'

const integer = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 0 })
const oneDecimal = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 1 })

export function formatValue(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined) return 'Saknas'
  switch (unit) {
    case '%':
      return `${oneDecimal.format(value)} %`
    case 'ggr':
      return `${oneDecimal.format(value)} ggr`
    case 'kvm':
      return `${integer.format(value)} m²`
    case 'kr/kvm':
      return `${integer.format(value)} kr/m²`
    case 'kr':
      return formatKronor(value)
    default:
      return `${oneDecimal.format(value)} ${unit}`
  }
}

/** Large amounts in millions, with the exact amount available in the source details. */
export function formatKronor(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `${oneDecimal.format(value / 1_000_000)} mkr`
  return `${integer.format(value)} kr`
}

export function formatExact(value: number, unit: string): string {
  const text = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 2 }).format(value)
  return unit === 'kr' ? `${text} kr` : `${text} ${unit === 'kvm' ? 'm²' : unit}`
}

export const STATUS_LABELS: Record<VerificationStatus, string> = {
  verified: 'Kontrollerad',
  extracted: 'Från dokument',
  user_entered: 'Manuellt angiven',
  calculated: 'Beräknad',
  estimated: 'Uppskattning',
  missing: 'Saknas',
  conflicting: 'Motstridiga uppgifter',
}

export const STATUS_DESCRIPTIONS: Record<VerificationStatus, string> = {
  verified: 'Du har kontrollerat värdet mot källan.',
  extracted: 'Läst automatiskt ur dokumentet. Inte kontrollerat.',
  user_entered: 'Angivet manuellt av dig.',
  calculated: 'Beräknat av appen utifrån andra värden.',
  estimated: 'En uppskattning med antaganden, inte ett faktiskt värde.',
  missing: 'Finns inte i några källor.',
  conflicting: 'Källorna eller beräkningen ger olika värden. Kontrollera.',
}

export const METHOD_LABELS: Record<string, string> = {
  pdf_key_figures_table: 'Flerårsöversikt / nyckeltal',
  pdf_financial_statement: 'Resultat- eller balansräkning',
  pdf_text_pattern: 'Löptext i dokumentet',
  manual: 'Manuellt angivet',
}

export const CONCERN_ORDER: ConcernLevel[] = ['high', 'moderate', 'low', 'insufficient_information']

export const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  annual_report: 'Årsredovisning',
  economic_plan: 'Ekonomisk plan',
  maintenance_plan: 'Underhållsplan',
  other: 'Övrigt dokument',
}

export const EXTRACTION_STATUS_LABELS: Record<string, string> = {
  succeeded: 'Analyserad',
  partial: 'Delvis analyserad',
  needs_ocr: 'Inskannad – kräver OCR',
  failed: 'Kunde inte läsas',
}

export const LAND_TENURE_LABELS: Record<string, string> = {
  owned: 'Äganderätt (egen mark)',
  leasehold: 'Tomträtt',
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('sv-SE')
}
