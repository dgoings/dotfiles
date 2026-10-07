import type { Spend } from '../types'

export const FIVE_HOURS_MS = 5 * 3_600_000
export const SEVEN_DAYS_MS = 7 * 86_400_000

/**
 * Elapsed share of a rate-limit window, 0..100: where usage would sit if the
 * whole allowance were burned evenly across the window. Null without a reset time.
 */
export const pace = (lengthMs: number, resetsAt: string | undefined, nowMs: number): number | null => {
  if (!resetsAt) return null
  const resets = Date.parse(resetsAt)
  if (Number.isNaN(resets)) return null
  const elapsed = Math.floor(((lengthMs - (resets - nowMs)) * 100) / lengthMs)
  return Math.min(100, Math.max(0, elapsed))
}

/**
 * A model id as /model shows it: `claude-fable-5-1` is `Fable 5.1`. A date suffix and
 * a bracketed variant (`[1m]`) are dropped; anything not shaped like an id is kept.
 */
export const modelName = (id: string): string => {
  const m = /^claude-([a-z]+)-(\d+)-(\d+)(?:-\d{8})?(?:\[.*\])?$/.exec(id)
  if (m === null) return id
  const [, family = '', major, minor] = m
  return `${family.charAt(0).toUpperCase()}${family.slice(1)} ${major}.${minor}`
}

export type MeterRun = { glyphs: string; kind: 'filled' | 'empty' | 'tick' }

/**
 * A meter of `cells` cells: usage filled from the left, the pace reference a tick at
 * its position (over a filled cell when usage has passed it), as runs of like cells.
 */
export const meter = (percent: number, paceAt: number | null, cells: number): MeterRun[] => {
  const clamp = (n: number, hi: number) => Math.min(hi, Math.max(0, n))
  const filled = clamp(Math.round((percent / 100) * cells), cells)
  const tick = paceAt === null ? -1 : clamp(Math.floor((paceAt / 100) * cells), cells - 1)
  const runs: MeterRun[] = []
  for (let i = 0; i < cells; i++) {
    const kind: MeterRun['kind'] = i === tick ? 'tick' : i < filled ? 'filled' : 'empty'
    const glyph = kind === 'tick' ? '┆' : kind === 'filled' ? '█' : '░'
    const last = runs[runs.length - 1]
    if (last !== undefined && last.kind === kind) last.glyphs += glyph
    else runs.push({ glyphs: glyph, kind })
  }
  return runs
}

/** Theme key for a used-percentage: green under 50, yellow under 80, red from 80. */
export const tier = (percent: number): 'success' | 'warning' | 'error' =>
  percent >= 80 ? 'error' : percent >= 50 ? 'warning' : 'success'

const two = (n: number) => String(n).padStart(2, '0')

/** A reset time as local HH:MM. */
export const clock = (iso: string): string => {
  const d = new Date(iso)
  return `${two(d.getHours())}:${two(d.getMinutes())}`
}

/**
 * Start of the current weekly window, in epoch milliseconds. Preferred source is
 * the reset time the API reports, so the local scan covers the same span as the
 * 7d percentage it is scaled against. Falls back to the local calendar (Thursday
 * 17:00) when no reading exists yet, derived from the calendar rather than by
 * subtracting seven days, so a DST change does not walk the boundary an hour off.
 */
export const weekWindowStart = (resetsAt: string | undefined, nowMs: number): number => {
  const resets = resetsAt ? Date.parse(resetsAt) : NaN
  if (!Number.isNaN(resets)) return resets - SEVEN_DAYS_MS
  const now = new Date(nowMs)
  let daysBack = (now.getDay() - 4 + 7) % 7 // 4 = Thursday
  if (daysBack === 0 && now.getHours() < 17) daysBack = 7
  return new Date(now.getFullYear(), now.getMonth(), now.getDate() - daysBack, 17, 0, 0, 0).getTime()
}

type Family = 'fable' | 'opus' | 'sonnet' | 'haiku'

/** List rates per MTok: input, output, cache read, 5m cache write, 1h cache write. */
const RATES: Record<Family, [number, number, number, number, number]> = {
  fable: [10, 50, 1, 12.5, 20],
  opus: [5, 25, 0.5, 6.25, 10],
  sonnet: [3, 15, 0.3, 3.75, 6],
  haiku: [1, 5, 0.1, 1.25, 2],
}

/** Unrecognized models are priced as Opus, the common case. */
const family = (model: string): Family => {
  if (/^claude-(fable|mythos)/.test(model)) return 'fable'
  if (/^claude-sonnet/.test(model)) return 'sonnet'
  if (/^claude-haiku/.test(model)) return 'haiku'
  return 'opus'
}

/**
 * Prices the scan's rows (id, model, input, output, cache read, 5m write, 1h write,
 * tab-separated). One API response can appear many times: streaming writes a row per
 * progress snapshot, and resuming or forking a session copies the whole transcript
 * into a new file. Snapshots repeat identical input and cache counts while output
 * grows, so each id is counted once, with the largest output seen.
 */
export const priceRows = (tsv: string): Spend => {
  const rows = new Map<string, { model: string; counts: number[] }>()
  for (const line of tsv.split('\n')) {
    if (line === '') continue
    const [id = '?', model = 'unknown', ...rest] = line.split('\t')
    const counts = rest.map(n => Number(n) || 0)
    const seen = rows.get(id)
    if (seen === undefined) rows.set(id, { model, counts })
    else seen.counts[1] = Math.max(seen.counts[1] ?? 0, counts[1] ?? 0)
  }
  const spend: Spend = { fable: 0, all: 0 }
  for (const { model, counts } of rows.values()) {
    const fam = family(model)
    const usd = RATES[fam].reduce((sum, rate, i) => sum + (counts[i] ?? 0) * rate, 0) / 1e6
    spend.all += usd
    if (fam === 'fable') spend.fable += usd
  }
  return spend
}

/**
 * Fable weekly usage as an estimated percentage of the plan's Fable sub-limit:
 * 7d% x (fable spend / all spend) / share. The dollar amounts cancel, so the
 * weekly allowance is never hardcoded. Null (nothing to show) without spend.
 */
export const fablePercent = (weekPercent: number, spend: Spend | null, share: number): number | null => {
  if (spend === null || !(spend.all > 0) || !(share > 0)) return null
  return Math.round((weekPercent * (spend.fable / spend.all)) / share)
}

// Reads transcripts as raw lines and parses each individually: a transcript
// truncated mid-write leaves a partial final line, and parsing the file as JSON
// would abort the whole scan on it. Timestamps are UTC with fractional seconds,
// which fromdateiso8601 rejects, so the fraction is stripped before comparing.
// Rows are folded per message id here so the output stays small; priceRows folds
// again, since find may run jq in several batches.
const JQ_FILTER = `
reduce (
  inputs | fromjson? | objects
  | select(.type == "assistant")
  | select((.timestamp // "") | sub("\\\\.[0-9]+Z$"; "Z") | fromdateiso8601? // 0 | . >= $since)
) as $m ({};
  ($m.message.id // "?") as $id | ($m.message.usage // {}) as $u
  | if has($id) then .[$id].o = ([.[$id].o, ($u.output_tokens // 0)] | max)
    else .[$id] = {
      m: ($m.message.model // "unknown"),
      i: ($u.input_tokens // 0), o: ($u.output_tokens // 0), r: ($u.cache_read_input_tokens // 0),
      w5: ($u.cache_creation.ephemeral_5m_input_tokens // 0), w1: ($u.cache_creation.ephemeral_1h_input_tokens // 0)
    } end)
| to_entries[] | [.key, .value.m, .value.i, .value.o, .value.r, .value.w5, .value.w1] | @tsv
`

const localStamp = (ms: number): string => {
  const d = new Date(ms)
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`
}

/**
 * The scan as an argument vector: every transcript under `projectsDir` written
 * since the window opened (subagent transcripts in subagents/ included; they are a
 * large share of real usage), piped through jq in as few invocations as find allows.
 */
export const scanCommand = (projectsDir: string, windowStartMs: number): string[] => [
  'find', projectsDir, '-name', '*.jsonl', '-newermt', localStamp(windowStartMs),
  '-exec', 'jq', '-nrR', '--argjson', 'since', String(Math.floor(windowStartMs / 1000)), JQ_FILTER, '{}', '+',
]
