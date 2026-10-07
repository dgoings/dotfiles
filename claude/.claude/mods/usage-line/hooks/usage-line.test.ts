import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

import { fablePercent, meter, modelName, pace, priceRows, weekWindowStart } from './usage'

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

describe('the band', () => {
  const stubWorld = (on: On) => {
    const clock = mock.clock(on, { now: NOW })
    mock.store(on)
    mock.env(on, { HOME: '/home/t' })
    const runs: string[][] = []
    const world = { model: 'claude-fable-5-1' }
    on('session.start', (_$, e) => ({ cwd: e.cwd }))
    on('session.measure', (_$, e) => ({ changed: e.changed }))
    on('classic.PostModelSwitch', () => ({}))
    on('ui.render', () => ({ type: 'Box', props: {}, children: [] }))
    on('session.model', () => ({ value: world.model }))
    on('session.usage', () => ({ value: { startedAt: NOW, context: { window: 1_000_000 }, rateLimits: LIMITS } }))
    on('process.run', (_$, e) => {
      runs.push([...e.argv])
      return { value: { exitCode: 0, stdout: SCAN, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    })
    return { clock, runs, world }
  }

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
