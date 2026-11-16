import type { ServiceReading, ServiceWindow } from '../types'

export type { ServiceReading, ServiceWindow }

/** Claude Code's usage service, the one `/usage` reads. Internal and undocumented. */
export const USAGE_URL = 'https://api.anthropic.com/api/oauth/usage'

type Json = Record<string, unknown>

const isObject = (v: unknown): v is Json => typeof v === 'object' && v !== null && !Array.isArray(v)
const finite = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

const readWindow = (v: unknown): ServiceWindow | null => {
  if (!isObject(v)) return null
  const percentUsed = finite(v.utilization)
  if (percentUsed === null) return null
  const resetsAt = v.resets_at
  return typeof resetsAt === 'string' && !Number.isNaN(Date.parse(resetsAt)) ? { percentUsed, resetsAt } : { percentUsed }
}

const isFableLimit = (v: unknown): v is Json =>
  isObject(v) && v.kind === 'weekly_scoped' && isObject(v.scope) && isObject(v.scope.model) && v.scope.model.display_name === 'Fable'

/**
 * The service's answer as the gauges read it. Tolerant by design: a missing or mistyped
 * field makes only its own gauge null. Null when the text is not a JSON object or carries
 * neither the 5-hour nor the 7-day window.
 */
export const parseUsage = (text: string, at: number): ServiceReading | null => {
  let body: unknown
  try {
    body = JSON.parse(text)
  } catch {
    return null
  }
  if (!isObject(body)) return null
  const five = readWindow(body.five_hour)
  const week = readWindow(body.seven_day)
  if (five === null && week === null) return null
  const limit = Array.isArray(body.limits) ? body.limits.find(isFableLimit) : undefined
  return { at, five, week, fable: finite(limit?.percent) }
}
