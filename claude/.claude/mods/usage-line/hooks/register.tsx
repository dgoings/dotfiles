import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { RateWindow, ReadingKind, ServiceReading, SharedReading, SharedReadings, Snapshot, Spend } from '../types'
import { clockBody, renderClock, type ClockFigures } from './clock'
import { USAGE_URL, parseUsage } from './service'
import { FIVE_HOURS_MS, SEVEN_DAYS_MS, chooseGauges, chooseWindows, clock, meter, modelName, pace, priceRows, scanCommand, tier, weekWindowStart } from './usage'

const snapshot = atom({ plugin: 'usage-line', key: 'snapshot' } as const, null as Snapshot | null)

const TICK_MS = 60_000
const SCAN_TTL_MS = 120_000
const SCAN_TIMEOUT_MS = 60_000
// Three ticks, so a frame does not lapse between pushes while a session is open.
const FRAME_SEC = 180
// A push still pending after this long is abandoned, so a dead clock cannot block the next.
const PUSH_STALE_MS = 10_000
// However many sessions are open, the usage service is asked at most about every five
// minutes: it rate-limited the mod when asked every minute. Ten seconds under five ticks on
// purpose: an attempt is stamped a moment after its tick, so a full five minutes here would
// make the fifth tick fall just short and stretch the wait to six.
const SERVICE_TTL_MS = 5 * TICK_MS - 10_000
// After a failed request the wait grows by ten minutes a failure, to thirty at most, with
// the same slack under a whole number of ticks.
const SERVICE_BACKOFF_MS = 10 * TICK_MS
const SERVICE_BACKOFF_MAX = 3

const serviceWait = (failures: number) =>
  failures === 0 ? SERVICE_TTL_MS : Math.min(failures, SERVICE_BACKOFF_MAX) * SERVICE_BACKOFF_MS - 10_000

type ScanCache = { at: number; windowStart: number; spend: Spend }
// Shared between sessions: when one last asked the service, the last reading it got, and how
// many requests in a row have failed since, so every session honours the same back-off.
type ServiceCache = { attemptAt: number; reading: ServiceReading | null; failures: number }

// A session start's readings are of unknown age: a resumed session can hand back old numbers.
const UNKNOWN_AGE = 0
const KINDS: readonly ReadingKind[] = ['five_hour', 'seven_day']

const patch = ($: EngineInterface, fields: Partial<Snapshot>) =>
  update($, snapshot, s => ({ model: '', spend: null, now: 0, service: null, readings: null, ...s, ...fields }))

// Prices the week's transcripts, at most once per SCAN_TTL_MS per weekly window,
// and stamps `now` so the pace references and reset clocks move between turns.
const scan = async ($: EngineInterface) => {
  try {
    const now = await $.clock.now()
    const s = await read($, snapshot)
    const windowStart = weekWindowStart(s ? chooseWindows(s).week?.resetsAt : undefined, now)
    const cached = (await $.store.get('scan')) as ScanCache | undefined
    if (cached && cached.windowStart === windowStart && now - cached.at < SCAN_TTL_MS) {
      await patch($, { spend: cached.spend, now })
      return
    }
    const home = (await $.env.get('HOME')) ?? ''
    const ran = await $.process.run(scanCommand(`${home}/.claude/projects`, windowStart), { timeoutMs: SCAN_TIMEOUT_MS })
    const spend = ran.isStdoutTruncated ? null : priceRows(ran.stdout)
    if (spend) await $.store.set('scan', { at: now, windowStart, spend } satisfies ScanCache)
    await patch($, { spend, now })
  } catch {
    // A failed scan leaves the last estimate standing; the next tick tries again.
  }
}

/** The gauges as the band draws them, for the clock. */
const clockFigures = (s: Snapshot, fableShare: number): ClockFigures => {
  const g = chooseGauges(s, fableShare)
  return {
    five: g.five ? { percent: Math.round(g.five.percentUsed), pace: pace(FIVE_HOURS_MS, g.five.resetsAt, s.now) } : null,
    week: g.week ? { percent: Math.round(g.week.percentUsed), pace: pace(SEVEN_DAYS_MS, g.week.resetsAt, s.now) } : null,
    fable: g.fable,
    isFableExact: g.isFableExact,
  }
}

// Where frames go, and when the push in flight started (by $.clock.now()), null when none is pending.
type ClockTarget = { url: string; fableShare: number; pushStartedAt: number | null }

// Sends the current figures to the clock without waiting for it to answer.
const push = async ($: EngineInterface, target: ClockTarget | null) => {
  if (target === null) return
  try {
    const s = await read($, snapshot)
    const now = await $.clock.now()
    if (s === null || (target.pushStartedAt !== null && now - target.pushStartedAt < PUSH_STALE_MS)) return
    target.pushStartedAt = now
    const body = clockBody(renderClock(clockFigures(s, target.fableShare)), FRAME_SEC)
    void $.http
      .fetch(target.url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })
      .catch(() => {})
      .finally(() => {
        if (target.pushStartedAt === now) target.pushStartedAt = null
      })
  } catch {
    // The clock is a mirror; nothing it does may break a hook.
  }
}

// A stored entry is trusted only in the shape this version writes: anything else (a hand
// edit, a partial write, another version's entry) counts as absent. An entry with no failure
// count, as the version before the back-off wrote, counts as none failed.
const asServiceCache = (value: unknown): ServiceCache | undefined => {
  if (typeof value !== 'object' || value === null) return undefined
  const { attemptAt, reading, failures = 0 } = value as { attemptAt?: unknown; reading?: unknown; failures?: unknown }
  if (typeof attemptAt !== 'number') return undefined
  if (typeof failures !== 'number' || !Number.isInteger(failures) || failures < 0) return undefined
  if (reading === null) return { attemptAt, reading: null, failures }
  if (typeof reading !== 'object' || reading === undefined) return undefined
  return typeof (reading as { at?: unknown }).at === 'number' ? { attemptAt, reading: reading as ServiceReading, failures } : undefined
}

// The same, per window, for the sessions' shared readings: a window in any other shape counts as absent.
const asSharedReadings = (value: unknown): SharedReadings => {
  const shared: SharedReadings = {}
  if (typeof value !== 'object' || value === null) return shared
  for (const kind of KINDS) {
    const r = (value as Record<string, unknown>)[kind]
    if (typeof r !== 'object' || r === null) continue
    const { at, percentUsed, resetsAt } = r as { at?: unknown; percentUsed?: unknown; resetsAt?: unknown }
    if (typeof at !== 'number' || typeof percentUsed !== 'number') continue
    if (resetsAt === undefined) shared[kind] = { at, percentUsed }
    else if (typeof resetsAt === 'string') shared[kind] = { at, percentUsed, resetsAt }
  }
  return shared
}

// Shares this session's readings with the others. A measurement (`at` its time) replaces the
// stored reading of its window; a session start's (`at` null) only fills a window nothing is
// stored for, since its age is unknown.
const shareReadings = async ($: EngineInterface, windows: RateWindow[], at: number | null) => {
  try {
    const shared = asSharedReadings(await $.store.get('readings'))
    let changed = false
    for (const kind of KINDS) {
      const w = windows.find(r => r.kind === kind)
      if (w === undefined || (at === null && shared[kind] !== undefined)) continue
      const reading: SharedReading = { at: at ?? UNKNOWN_AGE, percentUsed: w.percentUsed }
      if (w.resetsAt !== undefined) reading.resetsAt = w.resetsAt
      shared[kind] = reading
      changed = true
    }
    if (changed) await $.store.set('readings', shared)
  } catch {
    // Unshared, the reading is lost to the gauges until the next measurement.
  }
}

// Copies what the sessions share into this one's snapshot, and moves `now`, so every session
// draws the same figures from the same record, and a reading ages even while the scan fails.
const readShared = async ($: EngineInterface) => {
  try {
    const [now, service, readings] = await Promise.all([$.clock.now(), $.store.get('service'), $.store.get('readings')])
    await patch($, { service: asServiceCache(service)?.reading ?? null, readings: asSharedReadings(readings), now })
  } catch {
    // The snapshot keeps the last copy; the next push or tick tries again.
  }
}

// Draws afresh: the band through the snapshot, the clock through a push. The shared record is
// read first, so a push one session makes never draws older data than another's last push.
const draw = async ($: EngineInterface, target: ClockTarget | null) => {
  await readShared($)
  await push($, target)
}

// Claims the next request to the service when the last attempt was long enough ago (longer
// after failures), answering the credential to make it with. The claim is stored before any
// request goes out, so other sessions, and a request that hangs, do not pile up. A session
// with no credential never claims: it could not ask, and its claim would keep a session that
// can from asking.
const claimService = async ($: EngineInterface): Promise<string | null> => {
  try {
    const now = await $.clock.now()
    const cached = asServiceCache(await $.store.get('service'))
    if (cached && now - cached.attemptAt < serviceWait(cached.failures)) return null
    const auth = await $.session.authorize()
    if (auth === null) return null
    await $.store.set('service', { attemptAt: now, reading: cached?.reading ?? null, failures: cached?.failures ?? 0 } satisfies ServiceCache)
    return auth.handle
  } catch {
    return null
  }
}

type ServiceFailure = { status: number | null; retryAfter: string | null; text: string }

// Counts a failed request in the shared entry, which lengthens every session's wait for the
// next, and notes why under `serviceFailure` for whoever has to work out why the service
// reading went stale. Neither write may throw: this runs where nothing would catch it.
const recordFailure = async ($: EngineInterface, failure: ServiceFailure) => {
  let now = 0
  try {
    now = await $.clock.now()
    const cached = asServiceCache(await $.store.get('service'))
    await $.store.set('service', {
      attemptAt: cached?.attemptAt ?? now,
      reading: cached?.reading ?? null,
      failures: (cached?.failures ?? 0) + 1,
    } satisfies ServiceCache)
  } catch {
    // Uncounted, the failure only shortens the wait before the next attempt.
  }
  try {
    await $.store.set('serviceFailure', { at: now, ...failure })
  } catch {
    // The note is a diagnostic; losing it changes nothing drawn.
  }
}

// Asks the service, and on a usable answer shares the reading and draws it. A failed or
// refused request, or an answer it cannot read, leaves the last reading standing and backs off.
const fetchService = async ($: EngineInterface, target: ClockTarget | null, handle: string) => {
  let failure: ServiceFailure
  try {
    const res = await $.http.fetch(USAGE_URL, { auth: handle, headers: { 'anthropic-beta': 'oauth-2025-04-20' } })
    const reading = res.ok ? parseUsage(res.text, await $.clock.now()) : null
    if (reading !== null) {
      const cached = asServiceCache(await $.store.get('service'))
      await $.store.set('service', { attemptAt: cached?.attemptAt ?? reading.at, reading, failures: 0 } satisfies ServiceCache)
      await draw($, target)
      return
    }
    failure = { status: res.status, retryAfter: res.headers['retry-after'] ?? null, text: res.text.slice(0, 300) }
  } catch (error) {
    // The service is an upgrade over the sessions' shared readings; nothing it does may break a hook.
    failure = { status: null, retryAfter: null, text: String(error).slice(0, 300) }
  }
  await recordFailure($, failure)
}

// The timer's work, never awaited by a hook. The service request is not awaited even
// here, so one that hangs cannot hold back the scan or the clock on later ticks.
const refresh = async ($: EngineInterface, target: ClockTarget | null) => {
  // First, so the scan reads the 7d window the sessions share.
  await readShared($)
  await scan($)
  const handle = await claimService($)
  await draw($, target)
  if (handle !== null) void fetchService($, target, handle)
}

export const register: Register = (on, options) => {
  const configured = Number(options.fableShare)
  const fableShare = Number.isFinite(configured) && configured > 0 ? configured : 0.4
  const clockUrl = String(options.clockUrl ?? '').trim()
  const target: ClockTarget | null = /^https?:\/\/[^/\s]+/.test(clockUrl)
    ? { url: `${clockUrl.replace(/\/+$/, '')}/api/custom?name=usage`, fableShare, pushStartedAt: null }
    : null

  on('session.start', async ($, e, next) => {
    const [model, usage] = await Promise.all([$.session.model(), $.session.usage()])
    await patch($, { model: modelName(model) })
    await shareReadings($, usage.rateLimits, null)
    await draw($, target)
    $.clock.after(1_000, () => void refresh($, target))
    $.clock.every(TICK_MS, () => void refresh($, target))
    return next(e)
  })

  on('session.measure', async ($, e, next) => {
    await shareReadings($, e.rateLimits, await $.clock.now())
    await draw($, target)
    return next(e)
  })

  on('classic.PostModelSwitch', async ($, e, next) => {
    await patch($, { model: modelName(await $.session.model()) })
    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = await read($, snapshot)
    if (e.props.hasSurvey || s === null) return next(e)

    const { Box, Text } = $.ui.resolve(e)
    const { five, week, fable, isFableExact } = chooseGauges(s, fableShare)

    // Under about 96 columns the line would wrap, so the reset time goes first.
    const wide = e.props.bodyColumns >= 96

    const gauge = (label: string, percent: number, paceAt: number | null, prefix = '') => {
      const colour = tier(percent)
      const bar = meter(percent, paceAt, 10).map(run =>
        run.kind === 'filled' ? <Text color={colour}>{run.glyphs}</Text>
        : run.kind === 'tick' && percent > paceAt! ? <Text color={colour}>{run.glyphs}</Text>
        : <Text dimColor>{run.glyphs}</Text>,
      )
      return [<Text>{`   ${label} `}</Text>, ...bar, <Text color={colour}>{` ${prefix}${percent}%`}</Text>]
    }

    const parts = [<Text bold>{s.model}</Text>]
    if (five) {
      parts.push(...gauge('5h', Math.round(five.percentUsed), pace(FIVE_HOURS_MS, five.resetsAt, s.now)))
      if (wide && five.resetsAt) parts.push(<Text dimColor>{` resets ${clock(five.resetsAt)}`}</Text>)
    }
    // The Fable bar shares the 7d window, so its pace reference covers both.
    if (week) parts.push(...gauge('7d', Math.round(week.percentUsed), pace(SEVEN_DAYS_MS, week.resetsAt, s.now)))
    // Tilde marks the local estimate; a figure the usage service reported, even 0, has none.
    if (isFableExact) parts.push(...gauge('Fable', fable!, null))
    else if (fable) parts.push(...gauge('Fable', fable, null, '~'))

    // The margin and the dim border keep the line off the transcript's last row.
    return (
      <Box key="usage" marginTop={1} borderStyle="round" borderDimColor paddingX={1}>
        {parts}
      </Box>
    )
  })
}
