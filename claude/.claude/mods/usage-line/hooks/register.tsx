import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Snapshot, Spend } from '../types'
import { clockBody, renderClock, type ClockFigures } from './clock'
import { FIVE_HOURS_MS, SEVEN_DAYS_MS, clock, fablePercent, meter, modelName, pace, priceRows, scanCommand, tier, weekWindowStart } from './usage'

const snapshot = atom({ plugin: 'usage-line', key: 'snapshot' } as const, null as Snapshot | null)

const TICK_MS = 60_000
const SCAN_TTL_MS = 120_000
const SCAN_TIMEOUT_MS = 60_000
// Three ticks, so a frame does not lapse between pushes while a session is open.
const FRAME_SEC = 180
// A push still pending after this long is abandoned, so a dead clock cannot block the next.
const PUSH_STALE_MS = 10_000

type ScanCache = { at: number; windowStart: number; spend: Spend }

const patch = ($: EngineInterface, fields: Partial<Snapshot>) =>
  update($, snapshot, s => ({ model: '', rateLimits: [], spend: null, now: 0, ...s, ...fields }))

// Prices the week's transcripts, at most once per SCAN_TTL_MS per weekly window,
// and stamps `now` so the pace references and reset clocks move between turns.
const scan = async ($: EngineInterface) => {
  try {
    const now = await $.clock.now()
    const week = (await read($, snapshot))?.rateLimits.find(w => w.kind === 'seven_day')
    const windowStart = weekWindowStart(week?.resetsAt, now)
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
  const five = s.rateLimits.find(w => w.kind === 'five_hour')
  const week = s.rateLimits.find(w => w.kind === 'seven_day')
  return {
    five: five ? { percent: Math.round(five.percentUsed), pace: pace(FIVE_HOURS_MS, five.resetsAt, s.now) } : null,
    week: week ? { percent: Math.round(week.percentUsed), pace: pace(SEVEN_DAYS_MS, week.resetsAt, s.now) } : null,
    fable: (week && fablePercent(week.percentUsed, s.spend, fableShare)) || null,
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

const refresh = async ($: EngineInterface, target: ClockTarget | null) => {
  await scan($)
  await push($, target)
}

export const register: Register = (on, options) => {
  const configured = Number(options.fableShare)
  const fableShare = Number.isFinite(configured) && configured > 0 ? configured : 0.4
  const clockUrl = String(options.clockUrl ?? '')
  const target: ClockTarget | null = /^https?:\/\//.test(clockUrl)
    ? { url: `${clockUrl.replace(/\/+$/, '')}/api/custom?name=usage`, fableShare, pushStartedAt: null }
    : null

  on('session.start', async ($, e, next) => {
    const [model, usage, now] = await Promise.all([$.session.model(), $.session.usage(), $.clock.now()])
    await patch($, { model: modelName(model), rateLimits: usage.rateLimits, now })
    await push($, target)
    $.clock.after(1_000, () => void refresh($, target))
    $.clock.every(TICK_MS, () => void refresh($, target))
    return next(e)
  })

  on('session.measure', async ($, e, next) => {
    await patch($, { rateLimits: e.rateLimits, now: await $.clock.now() })
    await push($, target)
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
    const five = s.rateLimits.find(w => w.kind === 'five_hour')
    const week = s.rateLimits.find(w => w.kind === 'seven_day')
    const fable = week ? fablePercent(week.percentUsed, s.spend, fableShare) : null

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
    // Tilde marks this as a local estimate, not a figure the API reported.
    if (fable) parts.push(...gauge('Fable', fable, null, '~'))

    // The margin and the dim border keep the line off the transcript's last row.
    return (
      <Box key="usage" marginTop={1} borderStyle="round" borderDimColor paddingX={1}>
        {parts}
      </Box>
    )
  })
}
