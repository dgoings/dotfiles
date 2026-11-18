import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

import type { Snapshot } from '../types'
import { renderClock } from './clock'
import { USAGE_URL } from './service'
import { SAMPLE } from './service.sample'
import { FIVE_HOURS_MS, SERVICE_FABLE_FRESH_MS, SEVEN_DAYS_MS, chooseGauges, fablePercent, meter, modelName, pace, priceRows, weekWindowStart } from './usage'

const HOUR = 3_600_000
const DAY = 24 * HOUR
const NOW = Date.parse('2026-10-07T18:00:00Z')

// One row per (id, model, input, output, cache read, 5m write, 1h write), as the jq
// extraction prints them. msg_1 appears twice: a streaming snapshot and the settled row.
const SCAN =
  [
    ['msg_1', 'claude-fable-5-1', 2, 261, 23323, 0, 32197],
    ['msg_1', 'claude-fable-5-1', 2, 400, 23323, 0, 32197],
    ['msg_2', 'claude-opus-5-5', 10, 100, 50000, 1000, 0],
  ]
    .map(row => row.join('\t'))
    .join('\n') + '\n'

// msg_1 priced as Fable, once, with its largest output: 2*10 + 400*50 + 23323*1 + 32197*20.
const FABLE_USD = (20 + 20000 + 23323 + 643940) / 1e6
// msg_2 priced as Opus: 10*5 + 100*25 + 50000*0.5 + 1000*6.25.
const OPUS_USD = (50 + 2500 + 25000 + 6250) / 1e6

const FIVE = { kind: 'five_hour', percentUsed: 23.5, resetsAt: new Date(NOW + 2 * HOUR).toISOString() }
const WEEK = { kind: 'seven_day', percentUsed: 44, resetsAt: new Date(NOW + 3.5 * DAY).toISOString() }
const LIMITS = [FIVE, WEEK]

const BAND = {
  hasSurvey: false,
  isWorking: false,
  isCollapsed: false,
  maxRows: 10,
  bodyColumns: 120,
  scroll: { offset: 0, bodyRows: 10 },
  view: {},
}

const near = (a: number, b: number) => Math.abs(a - b) < 1e-9

describe('priceRows', () => {
  test('prices each response once, by model family, taking the largest output seen', () => {
    const spend = priceRows(SCAN)
    expect(near(spend.fable, FABLE_USD)).toBe(true)
    expect(near(spend.all, FABLE_USD + OPUS_USD)).toBe(true)
  })

  test('prices an unknown model as Opus', () => {
    const spend = priceRows('msg_9\tclaude-next-9\t0\t100\t0\t0\t0\n')
    expect(spend.fable).toBe(0)
    expect(near(spend.all, (100 * 25) / 1e6)).toBe(true)
  })
})

describe('modelName', () => {
  test('reads a model id as /model shows it', () => {
    expect(modelName('claude-fable-5-1')).toBe('Fable 5.1')
    expect(modelName('claude-opus-5-5')).toBe('Opus 5.5')
    expect(modelName('claude-sonnet-4-5-20250929')).toBe('Sonnet 4.5')
    expect(modelName('claude-fable-5-1[1m]')).toBe('Fable 5.1')
  })

  test('leaves a display name or an unknown id alone', () => {
    expect(modelName('Fable 5.1')).toBe('Fable 5.1')
    expect(modelName('gpt-5')).toBe('gpt-5')
  })
})

describe('meter', () => {
  test('fills cells by percent and marks the pace position in the empty run', () => {
    expect(meter(16, 75, 10)).toEqual([
      { glyphs: '██', kind: 'filled' },
      { glyphs: '░░░░░', kind: 'empty' },
      { glyphs: '┆', kind: 'tick' },
      { glyphs: '░░', kind: 'empty' },
    ])
  })

  test('keeps the tick visible when usage has passed the pace', () => {
    expect(meter(80, 30, 10)).toEqual([
      { glyphs: '███', kind: 'filled' },
      { glyphs: '┆', kind: 'tick' },
      { glyphs: '████', kind: 'filled' },
      { glyphs: '░░', kind: 'empty' },
    ])
  })

  test('draws no tick without a pace, and clamps full and empty bars', () => {
    expect(meter(36, null, 10)).toEqual([
      { glyphs: '████', kind: 'filled' },
      { glyphs: '░░░░░░', kind: 'empty' },
    ])
    expect(meter(100, 100, 10)).toEqual([{ glyphs: '█████████', kind: 'filled' }, { glyphs: '┆', kind: 'tick' }])
    expect(meter(0, 0, 10)).toEqual([{ glyphs: '┆', kind: 'tick' }, { glyphs: '░░░░░░░░░', kind: 'empty' }])
  })
})

describe('pace', () => {
  test('is the elapsed share of the window, as a whole percent', () => {
    expect(pace(5 * HOUR, new Date(NOW + 2 * HOUR).toISOString(), NOW)).toBe(60)
  })

  test('is null without a reset time and clamps to 0..100', () => {
    expect(pace(5 * HOUR, undefined, NOW)).toBe(null)
    expect(pace(5 * HOUR, new Date(NOW + 9 * HOUR).toISOString(), NOW)).toBe(0)
    expect(pace(5 * HOUR, new Date(NOW - HOUR).toISOString(), NOW)).toBe(100)
  })
})

describe('fablePercent', () => {
  test('scales the reported 7d percent by the local Fable ratio over the share', () => {
    expect(fablePercent(44, { fable: 0.327, all: 1 }, 0.4)).toBe(36)
  })

  test('is null with no spend to scale against', () => {
    expect(fablePercent(44, { fable: 0, all: 0 }, 0.4)).toBe(null)
    expect(fablePercent(44, null, 0.4)).toBe(null)
  })
})

describe('weekWindowStart', () => {
  test('is seven days before the reported 7d reset', () => {
    const resetsAt = new Date(NOW + 3.5 * DAY).toISOString()
    expect(weekWindowStart(resetsAt, NOW)).toBe(NOW + 3.5 * DAY - 7 * DAY)
  })

  test('falls back to the most recent Thursday 17:00 local', () => {
    const start = new Date(weekWindowStart(undefined, NOW))
    expect(start.getDay()).toBe(4)
    expect(start.getHours()).toBe(17)
    expect(start.getMinutes()).toBe(0)
    expect(NOW - start.getTime()).toBeLessThan(7 * DAY)
    expect(NOW - start.getTime()).toBeGreaterThan(0)
  })
})

describe('chooseGauges', () => {
  const SVC = { at: NOW - 30_000, five: { percentUsed: 5 }, week: { percentUsed: 40 }, fable: 36 }
  const SPEND = priceRows(SCAN)
  const ESTIMATE = fablePercent(44, SPEND, 0.4)
  // What the sessions shared: both windows, measured a minute ago.
  const READINGS = {
    five_hour: { at: NOW - 60_000, percentUsed: 23.5, resetsAt: FIVE.resetsAt },
    seven_day: { at: NOW - 60_000, percentUsed: 44, resetsAt: WEEK.resetsAt },
  }
  const snap = (fields: Partial<Snapshot>): Snapshot => ({
    model: 'Fable 5.1', spend: SPEND, now: NOW, service: null, readings: READINGS, ...fields,
  })
  const TODAY = {
    five: { percentUsed: 23.5, resetsAt: FIVE.resetsAt },
    week: { percentUsed: 44, resetsAt: WEEK.resetsAt },
    fable: ESTIMATE,
    isFableExact: false,
  }

  test('without a service reading, draws the shared session readings and the estimate', () => {
    expect(ESTIMATE).toBe(Math.round((44 * (FABLE_USD / (FABLE_USD + OPUS_USD))) / 0.4))
    expect(chooseGauges(snap({}), 0.4)).toEqual(TODAY)
  })

  test('a newer service reading wins over older shared readings', () => {
    expect(chooseGauges(snap({ service: SVC }), 0.4)).toEqual({
      five: { percentUsed: 5 }, week: { percentUsed: 40 }, fable: 36, isFableExact: true,
    })
  })

  test('newer shared readings win over the service reading, but its Fable figure stays', () => {
    const readings = { five_hour: { ...READINGS.five_hour, at: NOW }, seven_day: { ...READINGS.seven_day, at: NOW } }
    expect(chooseGauges(snap({ service: SVC, readings }), 0.4)).toEqual({ ...TODAY, fable: 36, isFableExact: true })
  })

  test('picks the newest reading per gauge, so a window no session shared takes the service\'s', () => {
    const g = chooseGauges(snap({ service: SVC, readings: { seven_day: { ...READINGS.seven_day, at: NOW } } }), 0.4)
    expect(g.five).toEqual({ percentUsed: 5 })
    expect(g.week).toEqual({ percentUsed: 44, resetsAt: WEEK.resetsAt })
  })

  test('draws an old service reading rather than nothing', () => {
    const g = chooseGauges(snap({ service: { ...SVC, at: NOW - 2 * HOUR }, readings: null }), 0.4)
    expect(g.five).toEqual({ percentUsed: 5 })
    expect(g.week).toEqual({ percentUsed: 40 })
  })

  test('draws the service\'s Fable figure while under an hour old, the estimate from the 7d gauge after', () => {
    const young = chooseGauges(snap({ service: { ...SVC, at: NOW - SERVICE_FABLE_FRESH_MS + 1 }, readings: null }), 0.4)
    expect(young.fable).toBe(36)
    expect(young.isFableExact).toBe(true)
    const old = chooseGauges(snap({ service: { ...SVC, at: NOW - SERVICE_FABLE_FRESH_MS }, readings: null }), 0.4)
    expect(old.week).toEqual({ percentUsed: 40 })
    expect(old.fable).toBe(fablePercent(40, SPEND, 0.4))
    expect(old.isFableExact).toBe(false)
  })

  test('reads a window that has ended as 0% with no reset time', () => {
    const ended = { at: NOW - 6 * HOUR, percentUsed: 80, resetsAt: new Date(NOW - HOUR).toISOString() }
    expect(chooseGauges(snap({ readings: { ...READINGS, five_hour: ended } }), 0.4).five).toEqual({ percentUsed: 0 })
    const endsNow = { ...ended, resetsAt: new Date(NOW).toISOString() }
    expect(chooseGauges(snap({ readings: { ...READINGS, five_hour: endsNow } }), 0.4).five).toEqual({ percentUsed: 0 })
    const svc = { ...SVC, five: { percentUsed: 70, resetsAt: ended.resetsAt } }
    expect(chooseGauges(snap({ service: svc, readings: null }), 0.4).five).toEqual({ percentUsed: 0 })
  })

  test('an ended window gives way to a reading of a later window, though of unknown age', () => {
    const svc = { ...SVC, at: NOW - 6 * HOUR, five: { percentUsed: 70, resetsAt: new Date(NOW - HOUR).toISOString() } }
    const started = { at: 0, percentUsed: 12, resetsAt: FIVE.resetsAt }
    expect(chooseGauges(snap({ service: svc, readings: { five_hour: started } }), 0.4).five).toEqual({ percentUsed: 12, resetsAt: FIVE.resetsAt })
  })

  test('never draws a session\'s own readings, only what is shared', () => {
    const own = { ...snap({ readings: null }), rateLimits: LIMITS, rateLimitsAt: NOW } as Snapshot
    expect(chooseGauges(own, 0.4)).toEqual({ five: null, week: null, fable: null, isFableExact: false })
  })

  test('reads a snapshot an older version wrote, with no shared fields, as having no readings', () => {
    const old = { model: 'Fable 5.1', rateLimits: LIMITS, spend: SPEND, now: NOW } as unknown as Parameters<typeof chooseGauges>[0]
    expect(chooseGauges(old, 0.4)).toEqual({ five: null, week: null, fable: null, isFableExact: false })
    expect(chooseGauges(snap({ service: {} as never }), 0.4)).toEqual(TODAY)
  })

  test('falls back to the estimate, scaled from the 7d figure drawn, when the service has no Fable figure', () => {
    const g = chooseGauges(snap({ service: { ...SVC, fable: null } }), 0.4)
    expect(g.week).toEqual({ percentUsed: 40 })
    expect(g.fable).toBe(fablePercent(40, SPEND, 0.4))
    expect(g.isFableExact).toBe(false)
  })

  test('draws an exact Fable figure of 0', () => {
    const g = chooseGauges(snap({ service: { ...SVC, fable: 0 } }), 0.4)
    expect(g.fable).toBe(0)
    expect(g.isFableExact).toBe(true)
  })
})

type Request = { url: string; init?: { method?: string; headers?: Record<string, string>; body?: unknown; auth?: string } }

// No credential by default, so the mod never asks the usage service unless a test opts in
// by setting `world.auth`; `stored` pre-fills the store shared between sessions. The store is
// this stub's own, not mock.store's, so a test can read what the mod wrote (`store`) and make a
// key refuse writes (`world.unwritable`).
const stubWorld = (on: On, stored: Record<string, unknown> = {}) => {
  const clock = mock.clock(on, { now: NOW })
  mock.env(on, { HOME: '/home/t' })
  const runs: string[][] = []
  const world = {
    model: 'claude-fable-5-1',
    limits: LIMITS as typeof LIMITS | (typeof WEEK)[],
    auth: null as { handle: string; kind: 'bearer' } | null,
    unwritable: new Set<string>(),
  }
  // Values go through JSON, as the engine keeps them.
  const entries = new Map<string, unknown>(Object.entries(structuredClone(stored)))
  const store = (key: string) => entries.get(key)
  const put = (key: string, value: unknown) => entries.set(key, structuredClone(value))
  on('store.get', (_$, e) => ({ value: entries.get(e.key) }))
  on('store.set', (_$, e) => {
    if (world.unwritable.has(e.key)) throw new Error(`store refused ${e.key}`)
    entries.set(e.key, JSON.parse(JSON.stringify(e.value)))
    return { value: undefined }
  })
  on('store.delete', (_$, e) => {
    entries.delete(e.key)
    return { value: undefined }
  })
  on('store.keys', () => ({ value: [...entries.keys()] }))
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('session.measure', (_$, e) => ({ changed: e.changed }))
  on('classic.PostModelSwitch', () => ({}))
  on('ui.render', () => ({ type: 'Box', props: {}, children: [] }))
  on('session.model', () => ({ value: world.model }))
  on('session.usage', () => ({ value: { startedAt: NOW, context: { window: 1_000_000 }, rateLimits: world.limits } }))
  on('session.authorize', () => ({ value: world.auth }))
  on('process.run', (_$, e) => {
    runs.push([...e.argv])
    return { value: { exitCode: 0, stdout: SCAN, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  // Every request to the clock and to the usage service, kept apart, and what the stub answers each with.
  const requests: Request[] = []
  const serviceRequests: Request[] = []
  let answer: () => unknown = () => ({ value: { status: 200, ok: true, headers: {}, text: '{"code":200}' } })
  let serviceAnswer: () => unknown = () => ({ value: { status: 200, ok: true, headers: {}, text: SAMPLE } })
  on('http.fetch', (_$, e) => {
    if (e.url === USAGE_URL) {
      serviceRequests.push(e)
      return serviceAnswer() as never
    }
    requests.push(e)
    return answer() as never
  })
  const setAnswer = (next: () => unknown) => {
    answer = next
  }
  const setServiceAnswer = (next: () => unknown) => {
    serviceAnswer = next
  }
  return { clock, runs, world, store, put, requests, setAnswer, serviceRequests, setServiceAnswer }
}

describe('the band', () => {
  test('draws the model, each window with its pace and reset, and the Fable estimate', async ($, on) => {
    const { clock, runs } = stubWorld(on)
    await $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
    await clock.advance(1_000)

    const ui = await $.ui.mount({ plugin: 'usage-line', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    const text = (await ui.find({ key: 'usage' }))?.text ?? ''

    expect(text).toMatch(/^Fable 5\.1 {3}5h ██░░░░┆░░░ 24% resets \d\d:\d\d {3}7d ████░┆░░░░ 44% {3}Fable █+░* ~\d+%$/)
    // A blank row and a dim rounded border keep the line off the transcript's last row.
    const box = await ui.find({ key: 'usage' })
    expect(box?.props.marginTop).toBe(1)
    expect(box?.props.borderStyle).toBe('round')
    expect(box?.props.borderDimColor, `box props: ${JSON.stringify(box?.props)}`).toBe(true)
    expect((await ui.find({ type: 'Text', text: 'Fable 5.1' }))?.props.bold, 'model is bold').toBe(true)
    // 44 * (fable / all) / 0.40, from the scan above.
    const fable = Math.round((44 * (FABLE_USD / (FABLE_USD + OPUS_USD))) / 0.4)
    expect(text.endsWith(` ~${fable}%`), `ends with ~${fable}%: ${text}`).toBe(true)
    expect(runs.length).toBe(1)
    expect(runs[0]?.[0]).toBe('find')
    expect(runs[0]?.[1]).toBe('/home/t/.claude/projects')
  })

  test('colours a window by its usage tier', async ($, on) => {
    const { clock } = stubWorld(on)
    await $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
    await clock.advance(1_000)

    const ui = await $.ui.mount({ plugin: 'usage-line', surface: 'terminal', component: 'AbovePrompt', props: BAND })

    expect((await ui.find({ type: 'Text', text: '24%' }))?.props.color).toBe('success')
    expect((await ui.find({ type: 'Text', text: '██' }))?.props.color).toBe('success')
    expect((await ui.find({ type: 'Text', text: '44%' }))?.props.color).toBe('success')
  })

  test('follows a measurement and a model switch', async ($, on) => {
    const { clock, world } = stubWorld(on)
    await $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
    await clock.advance(1_000)

    const moved = [
      { ...FIVE, percentUsed: 81 },
      { ...WEEK, percentUsed: 55 },
    ]
    await $.session.measure({ context: { window: 1_000_000 }, rateLimits: moved, changed: ['rateLimits'] })
    world.model = 'claude-opus-5-5'
    await $.classic.PostModelSwitch({ from_model: 'claude-fable-5-1', to_model: 'claude-opus-5-5', requested_model: 'opus', source: 'command', context_tokens: 0 } as never)

    const ui = await $.ui.mount({ plugin: 'usage-line', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    const text = (await ui.find({ key: 'usage' }))?.text ?? ''

    expect(text.startsWith('Opus 5.5   5h ██████┆█░░ 81%')).toBe(true)
    expect((await ui.find({ type: 'Text', text: '81%' }))?.props.color).toBe('error')
    expect((await ui.find({ type: 'Text', text: '55%' }))?.props.color).toBe('warning')
  })

  test('drops the reset time on a narrow band', async ($, on) => {
    const { clock } = stubWorld(on)
    await $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
    await clock.advance(1_000)

    const ui = await $.ui.mount({ plugin: 'usage-line', surface: 'terminal', component: 'AbovePrompt', props: { ...BAND, bodyColumns: 80 } })
    const text = (await ui.find({ key: 'usage' }))?.text ?? ''

    expect(text).toMatch(/^Fable 5\.1 {3}5h ██░░░░┆░░░ 24% {3}7d /)
  })

  test('yields the band to a survey, and draws nothing before any figures', async ($, on) => {
    stubWorld(on)
    const quiet = await $.ui.mount({ plugin: 'usage-line', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    expect(await quiet.find({ key: 'usage' })).toBe(undefined)
    await quiet.unmount()

    await $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
    const survey = await $.ui.mount({ plugin: 'usage-line', surface: 'terminal', component: 'AbovePrompt', props: { ...BAND, hasSurvey: true } })
    expect(await survey.find({ key: 'usage' })).toBe(undefined)
  })
})

describe('the usage service', () => {
  const AUTH = { handle: 'handle-1', kind: 'bearer' as const }
  const start = ($: Parameters<TestBody>[0]) => $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
  const band = async ($: Parameters<TestBody>[0]) => {
    const ui = await $.ui.mount({ plugin: 'usage-line', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    return (await ui.find({ key: 'usage' }))?.text ?? ''
  }
  // The band as it is drawn from the session readings and the Fable estimate alone.
  const ESTIMATE = Math.round((44 * (FABLE_USD / (FABLE_USD + OPUS_USD))) / 0.4)
  const TODAY = new RegExp(`^Fable 5\\.1 {3}5h ██░░░░┆░░░ 24% resets \\d\\d:\\d\\d {3}7d ████░┆░░░░ 44% {3}Fable █+░* ~${ESTIMATE}%$`)

  test('draws all three gauges from the service, the Fable figure without a tilde', async ($, on) => {
    const { clock, world, serviceRequests } = stubWorld(on)
    world.auth = AUTH
    await start($)
    await clock.advance(1_000)

    // The service's readings are newer than the session's; its reset times are weeks out, so both pace ticks sit at 0.
    expect(await band($)).toMatch(/^Fable 5\.1 {3}5h ┆░{9} 0% resets \d\d:\d\d {3}7d ┆██░{7} 31% {3}Fable █{4}░{6} 36%$/)
    expect(serviceRequests.length).toBe(1)
    expect(serviceRequests[0]?.init?.auth).toBe('handle-1')
    expect(serviceRequests[0]?.init?.headers?.['anthropic-beta']).toBe('oauth-2025-04-20')
  })

  test('asks about every five minutes, not every tick or measurement', async ($, on) => {
    const { clock, world, serviceRequests } = stubWorld(on)
    world.auth = AUTH
    await start($)
    await clock.advance(1_000)
    expect(serviceRequests.length).toBe(1)
    await $.session.measure({ context: { window: 1_000_000 }, rateLimits: LIMITS, changed: ['rateLimits'] })
    await clock.set(NOW + 4 * 60_000) // the fourth tick
    expect(serviceRequests.length).toBe(1)
    await clock.set(NOW + 5 * 60_000) // the fifth tick, 299 s after the first request
    expect(serviceRequests.length).toBe(2)
    await clock.set(NOW + 9 * 60_000)
    expect(serviceRequests.length).toBe(2)
    await clock.set(NOW + 10 * 60_000)
    expect(serviceRequests.length).toBe(3)
  })

  const REFUSED = () => ({
    value: { status: 429, ok: false, headers: { 'retry-after': '0' }, text: '{"error":{"type":"rate_limit_error","message":"Rate limited. Please try again later."}}' },
  })

  test('backs off after each refusal: 10 minutes, then 20, then 30, and no more', async ($, on) => {
    const { clock, world, serviceRequests, setServiceAnswer, store } = stubWorld(on)
    world.auth = AUTH
    setServiceAnswer(REFUSED)
    await start($)
    await clock.advance(1_000)
    const MIN = 60_000
    // [when, requests so far]: attempts at 0:01, 10:00, 30:00, 60:00 and 90:00.
    const steps: [number, number][] = [
      [9 * MIN, 1], [10 * MIN, 2], [29 * MIN, 2], [30 * MIN, 3], [59 * MIN, 3], [60 * MIN, 4], [89 * MIN, 4], [90 * MIN, 5],
    ]
    for (const [at, count] of steps) {
      await clock.set(NOW + at)
      expect(serviceRequests.length, `requests by ${at / MIN} min`).toBe(count)
    }
    expect(((store('service')) as { failures?: number }).failures).toBe(5)
  })

  test('counts a thrown request and an unreadable answer as refusals too', async ($, on) => {
    const { clock, world, serviceRequests, setServiceAnswer, store } = stubWorld(on)
    world.auth = AUTH
    setServiceAnswer(() => { throw new Error('unreachable') })
    await start($)
    await clock.advance(1_000)
    setServiceAnswer(() => ({ value: { status: 200, ok: true, headers: {}, text: 'not json' } }))
    await clock.set(NOW + 9 * 60_000)
    expect(serviceRequests.length).toBe(1)
    await clock.set(NOW + 10 * 60_000)
    expect(serviceRequests.length).toBe(2)
    await clock.set(NOW + 29 * 60_000)
    expect(serviceRequests.length).toBe(2)
    expect(((store('service')) as { failures?: number }).failures).toBe(2)
  })

  test('returns to every five minutes after a success', async ($, on) => {
    const { clock, world, serviceRequests, setServiceAnswer, store } = stubWorld(on)
    world.auth = AUTH
    setServiceAnswer(REFUSED)
    await start($)
    await clock.advance(1_000)
    setServiceAnswer(() => ({ value: { status: 200, ok: true, headers: {}, text: SAMPLE } }))
    await clock.set(NOW + 10 * 60_000)
    expect(serviceRequests.length).toBe(2)
    expect(((store('service')) as { failures?: number }).failures).toBe(0)
    await clock.set(NOW + 14 * 60_000)
    expect(serviceRequests.length).toBe(2)
    await clock.set(NOW + 15 * 60_000)
    expect(serviceRequests.length).toBe(3)
  })

  test('honours a back-off another session stored', async ($, on) => {
    const { clock, world, serviceRequests } = stubWorld(on, { service: { attemptAt: NOW - 15 * 60_000, reading: null, failures: 2 } })
    world.auth = AUTH
    await start($)
    await clock.advance(1_000)
    expect(serviceRequests.length).toBe(0)
    await clock.set(NOW + 4 * 60_000)
    expect(serviceRequests.length).toBe(0)
    await clock.set(NOW + 5 * 60_000) // 20 minutes after that session's attempt
    expect(serviceRequests.length).toBe(1)
  })

  test('treats a stored failure count of another shape as an absent entry', async ($, on) => {
    const { clock, world, serviceRequests } = stubWorld(on, { service: { attemptAt: NOW - 10_000, reading: null, failures: 'two' } })
    world.auth = AUTH
    await start($)
    await clock.advance(1_000)
    expect(serviceRequests.length).toBe(1)
  })

  test('keeps a note of why the service last failed', async ($, on) => {
    const { clock, world, setServiceAnswer, store } = stubWorld(on)
    world.auth = AUTH
    setServiceAnswer(REFUSED)
    await start($)
    await clock.advance(1_000)
    expect(store('serviceFailure')).toEqual({
      at: NOW + 1_000, status: 429, retryAfter: '0', text: REFUSED().value.text,
    })
    setServiceAnswer(() => { throw new Error('unreachable') })
    await clock.set(NOW + 10 * 60_000)
    // The harness hands the plugin its own error for a stub that throws, so only the shape is checked.
    expect(store('serviceFailure')).toEqual({ at: NOW + 10 * 60_000, status: null, retryAfter: null, text: expect.stringMatching(/Error/) })
  })

  test('still backs off and draws when the note cannot be written', async ($, on) => {
    const { clock, world, serviceRequests, setServiceAnswer, store } = stubWorld(on)
    world.auth = AUTH
    world.unwritable.add('serviceFailure')
    setServiceAnswer(REFUSED)
    await start($)
    await clock.advance(1_000)
    expect(serviceRequests.length).toBe(1)
    expect(((store('service')) as { failures?: number }).failures).toBe(1)
    await clock.set(NOW + 9 * 60_000)
    expect(serviceRequests.length).toBe(1)
    expect(await band($)).toMatch(TODAY)
  })

  test('draws the last service reading, however old, while the service refuses', async ($, on) => {
    const at = NOW - 17 * 60_000
    const reading = { at, five: { percentUsed: 5 }, week: { percentUsed: 40 }, fable: 36 }
    const { clock, world, setServiceAnswer } = stubWorld(on, { service: { attemptAt: at, reading } })
    world.auth = AUTH
    world.limits = [WEEK] // a session handed no 5-hour window, as in T3 Code
    setServiceAnswer(REFUSED)
    await start($)
    await clock.advance(1_000)
    // 5h and Fable from the stored reading; 7d too, since the session's own is of unknown age.
    expect(await band($)).toMatch(/^Fable 5\.1 {3}5h █░{9} 5% {3}7d ████░{6} 40% {3}Fable █{4}░{6} 36%$/)
  })

  test('draws what another session fetched in the last minute, without asking again', async ($, on) => {
    const reading = { at: NOW - 10_000, five: { percentUsed: 5 }, week: { percentUsed: 40 }, fable: 36 }
    const { clock, world, serviceRequests } = stubWorld(on, { service: { attemptAt: NOW - 10_000, reading } })
    world.auth = AUTH
    world.limits = [WEEK] // a session handed no 5-hour window
    await start($)
    await clock.advance(1_000)

    expect(serviceRequests.length).toBe(0)
    // Both windows from the stored reading: a session's start reading is of unknown age, so it ranks below it.
    expect(await band($)).toMatch(/^Fable 5\.1 {3}5h █░{9} 5% {3}7d ████░{6} 40% {3}Fable █{4}░{6} 36%$/)
  })

  test('treats a stored entry of another shape as absent', async ($, on) => {
    const { clock, serviceRequests } = stubWorld(on, { service: { attemptAt: NOW - 10_000, reading: {} } })
    await start($)
    await clock.advance(1_000)
    expect(serviceRequests.length).toBe(0) // no credential in this world
    expect(await band($)).toMatch(TODAY)
  })

  test('draws an exact Fable figure of 0 as an empty bar', async ($, on) => {
    const reading = { at: NOW - 10_000, five: { percentUsed: 5 }, week: { percentUsed: 40 }, fable: 0 }
    const { clock } = stubWorld(on, { service: { attemptAt: NOW - 10_000, reading } })
    await start($)
    await clock.advance(1_000)
    expect((await band($)).endsWith('   Fable ░░░░░░░░░░ 0%')).toBe(true)
  })

  const failures: [string, () => unknown][] = [
    ['answers 500', () => ({ value: { status: 500, ok: false, headers: {}, text: SAMPLE } })],
    ['throws', () => { throw new Error('unreachable') }],
    ['answers with no JSON', () => ({ value: { status: 200, ok: true, headers: {}, text: 'not json' } })],
  ]
  for (const [what, answer] of failures) {
    test(`draws today's band when the service ${what}`, async ($, on) => {
      const { clock, world, serviceRequests, setServiceAnswer } = stubWorld(on)
      world.auth = AUTH
      setServiceAnswer(answer)
      await start($)
      await clock.advance(1_000)

      expect(serviceRequests.length).toBe(1)
      expect(await band($)).toMatch(TODAY)
    })
  }

  test('does not wait for, or pile up behind, a service that never answers', async ($, on) => {
    const { clock, world, serviceRequests, setServiceAnswer } = stubWorld(on)
    world.auth = AUTH
    setServiceAnswer(() => new Promise(() => {}))
    await start($)
    await clock.advance(1_000)
    expect(serviceRequests.length).toBe(1)
    await $.session.measure({ context: { window: 1_000_000 }, rateLimits: LIMITS, changed: ['rateLimits'] })
    await clock.advance(40_000)
    expect(serviceRequests.length).toBe(1)
    expect(await band($)).toMatch(TODAY)
  })

  test('makes no request to the service without a credential', async ($, on) => {
    const { clock, serviceRequests } = stubWorld(on)
    await start($)
    await clock.advance(121_000)
    expect(serviceRequests.length).toBe(0)
    expect(await band($)).toMatch(TODAY)
  })
})

describe('shared session readings', () => {
  const start = ($: Parameters<TestBody>[0]) => $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
  const band = async ($: Parameters<TestBody>[0]) => {
    const ui = await $.ui.mount({ plugin: 'usage-line', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    return (await ui.find({ key: 'usage' }))?.text ?? ''
  }

  test('shares a measurement, stamped with the time it was taken, over what was stored', async ($, on) => {
    const { clock, store } = stubWorld(on, { readings: { five_hour: { at: NOW - 60_000, percentUsed: 10 } } })
    await start($)
    await clock.advance(1_000)
    await $.session.measure({ context: { window: 1_000_000 }, rateLimits: [{ ...FIVE, percentUsed: 81 }, { ...WEEK, percentUsed: 55 }], changed: ['rateLimits'] })
    expect(store('readings')).toEqual({
      five_hour: { at: NOW + 1_000, percentUsed: 81, resetsAt: FIVE.resetsAt },
      seven_day: { at: NOW + 1_000, percentUsed: 55, resetsAt: WEEK.resetsAt },
    })
  })

  test('a session start fills only a window nothing is stored for, as of unknown age', async ($, on) => {
    const week = { at: NOW - 3 * DAY, percentUsed: 50, resetsAt: WEEK.resetsAt }
    const { clock, store } = stubWorld(on, { readings: { seven_day: week } })
    await start($)
    await clock.advance(1_000)
    expect(store('readings')).toEqual({
      five_hour: { at: 0, percentUsed: 23.5, resetsAt: FIVE.resetsAt },
      seven_day: week,
    })
    expect(await band($)).toMatch(/ 7d █████┆░░░░ 50% /)
  })

  test('treats a stored entry of another shape as absent', async ($, on) => {
    const { clock, store } = stubWorld(on, { readings: { five_hour: { at: 'x', percentUsed: 5 }, seven_day: 'junk' } })
    await start($)
    await clock.advance(1_000)
    expect(store('readings')).toEqual({
      five_hour: { at: 0, percentUsed: 23.5, resetsAt: FIVE.resetsAt },
      seven_day: { at: 0, percentUsed: 44, resetsAt: WEEK.resetsAt },
    })
  })

  test('draws what the sessions shared, not its own readings', { options: { clockUrl: 'http://clock.test/' } }, async ($, on) => {
    const readings = {
      five_hour: { at: NOW - 60_000, percentUsed: 70, resetsAt: FIVE.resetsAt },
      seven_day: { at: NOW - 60_000, percentUsed: 60, resetsAt: WEEK.resetsAt },
    }
    const { clock, requests } = stubWorld(on, { readings })
    await start($)
    await clock.advance(1_000)
    expect(await band($)).toMatch(/ 5h .* 70% .* 7d .* 60% /)
    const last = requests[requests.length - 1]
    const at = NOW + 1_000
    expect(JSON.parse(String(last?.init?.body)).draw[0].db[4]).toEqual(
      renderClock({
        five: { percent: 70, pace: pace(FIVE_HOURS_MS, FIVE.resetsAt, at) },
        week: { percent: 60, pace: pace(SEVEN_DAYS_MS, WEEK.resetsAt, at) },
        fable: fablePercent(60, priceRows(SCAN), 0.4),
      }),
    )
  })

  test('a push draws what another session shared since this one last looked', { options: { clockUrl: 'http://clock.test/' } }, async ($, on) => {
    const { clock, requests, store, put } = stubWorld(on)
    await start($)
    await clock.advance(1_000)
    // Another session measures a 5-hour window between this one's ticks.
    const stored = store('readings') as Record<string, unknown>
    put('readings', { ...stored, five_hour: { at: NOW + 2_000, percentUsed: 90, resetsAt: FIVE.resetsAt } })
    await clock.advance(1_000)
    await $.session.measure({ context: { window: 1_000_000 }, rateLimits: [{ ...WEEK, percentUsed: 55 }], changed: ['rateLimits'] })
    const last = requests[requests.length - 1]
    const at = NOW + 2_000
    expect(JSON.parse(String(last?.init?.body)).draw[0].db[4]).toEqual(
      renderClock({
        five: { percent: 90, pace: pace(FIVE_HOURS_MS, FIVE.resetsAt, at) },
        week: { percent: 55, pace: pace(SEVEN_DAYS_MS, WEEK.resetsAt, at) },
        fable: fablePercent(55, priceRows(SCAN), 0.4),
      }),
    )
  })
})

describe('the clock', () => {
  const CLOCK = { options: { clockUrl: 'http://clock.test/' } }
  const start = ($: Parameters<TestBody>[0]) => $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })

  test('posts the gauges to the clock as one bitmap frame', CLOCK, async ($, on) => {
    const { clock, requests } = stubWorld(on)
    await start($)
    await clock.advance(1_000)
    const last = requests[requests.length - 1]
    expect(last?.url).toBe('http://clock.test/api/custom?name=usage')
    expect(last?.init?.method).toBe('POST')
    expect(last?.init?.headers?.['Content-Type']).toBe('application/json')
    const body = JSON.parse(String(last?.init?.body))
    expect(body.duration).toBe(180)
    // The same figures the band test reads: 5h 24% with pace 60, 7d 44% with pace 50.
    const fable = Math.round((44 * (FABLE_USD / (FABLE_USD + OPUS_USD))) / 0.4)
    expect(body.draw[0].db[4]).toEqual(
      renderClock({ five: { percent: 24, pace: 60 }, week: { percent: 44, pace: 50 }, fable }),
    )
    expect(requests.every(r => r.url.includes('/api/custom?name=usage'))).toBe(true)
  })

  test('pushes again on a measurement and on the tick', CLOCK, async ($, on) => {
    const { clock, requests } = stubWorld(on)
    await start($)
    await clock.advance(1_000)
    const before = requests.length
    await $.session.measure({ context: { window: 1_000_000 }, rateLimits: [{ ...FIVE, percentUsed: 81 }, WEEK], changed: ['rateLimits'] })
    expect(requests.length).toBe(before + 1)
    await clock.advance(60_000)
    expect(requests.length).toBe(before + 2)
  })

  test('makes no request without a clock URL', async ($, on) => {
    const { clock, requests } = stubWorld(on)
    await start($)
    await clock.advance(61_000)
    expect(requests.length).toBe(0)
  })

  test('ignores a clock URL that is not http', { options: { clockUrl: 'clock.local' } }, async ($, on) => {
    const { clock, requests } = stubWorld(on)
    await start($)
    await clock.advance(61_000)
    expect(requests.length).toBe(0)
  })

  test('ignores a clock URL with no host', { options: { clockUrl: 'http://' } }, async ($, on) => {
    const { clock, requests } = stubWorld(on)
    await start($)
    await clock.advance(61_000)
    expect(requests.length).toBe(0)
  })

  test('tolerates spaces around the clock URL', { options: { clockUrl: ' http://clock.test ' } }, async ($, on) => {
    const { clock, requests } = stubWorld(on)
    await start($)
    await clock.advance(1_000)
    expect(requests.length > 0).toBe(true)
    expect(requests.every(r => r.url === 'http://clock.test/api/custom?name=usage')).toBe(true)
  })

  test('carries on when the clock refuses or errors', CLOCK, async ($, on) => {
    const { clock, setAnswer } = stubWorld(on)
    setAnswer(() => {
      throw new Error('unreachable')
    })
    await start($)
    await clock.advance(1_000)
    const ui = await $.ui.mount({ plugin: 'usage-line', surface: 'terminal', component: 'AbovePrompt', props: BAND })
    expect((await ui.find({ key: 'usage' }))?.text).toMatch(/5h/)
  })

  test('does not wait for, or queue behind, a clock that never answers', CLOCK, async ($, on) => {
    const { clock, requests, setAnswer } = stubWorld(on)
    setAnswer(() => new Promise(() => {}))
    await start($) // resolves although the first push never settles: a hook does not await it
    await clock.advance(1_000)
    expect(requests.length).toBe(1)
    await $.session.measure({ context: { window: 1_000_000 }, rateLimits: LIMITS, changed: ['rateLimits'] })
    expect(requests.length).toBe(1) // skipped: one still in flight
    await clock.advance(60_000)
    expect(requests.length).toBe(2) // the stale one is abandoned after 10 s
  })

  test('shows the service\'s 5H gauge for a session handed only a 7-day window', CLOCK, async ($, on) => {
    const { clock, world, requests } = stubWorld(on)
    world.auth = { handle: 'handle-1', kind: 'bearer' }
    world.limits = [WEEK]
    await start($)
    await clock.advance(1_000)
    const last = requests[requests.length - 1]
    expect(last?.url).toBe('http://clock.test/api/custom?name=usage')
    const at = NOW + 1_000
    expect(JSON.parse(String(last?.init?.body)).draw[0].db[4]).toEqual(
      renderClock({
        five: { percent: 0, pace: pace(FIVE_HOURS_MS, '2026-11-16T20:30:00.205053+00:00', at) },
        week: { percent: 31, pace: pace(SEVEN_DAYS_MS, '2026-11-19T21:00:00.205079+00:00', at) },
        fable: 36,
        isFableExact: true,
      }),
    )
  })
})
