import { describe, expect, test } from 'claude-code/testing'

import { parseUsage } from './service'
import { SAMPLE } from './service.sample'

describe('parseUsage', () => {
  test('reads the three gauges from a real response', () => {
    expect(parseUsage(SAMPLE, 1000)).toEqual({
      at: 1000,
      five: { percentUsed: 0, resetsAt: '2026-11-16T20:30:00.205053+00:00' },
      week: { percentUsed: 31, resetsAt: '2026-11-19T21:00:00.205079+00:00' },
      fable: 36,
    })
  })

  test('is null for text that is not a usage object', () => {
    for (const t of ['', 'not json', '[]', 'null', '{}', '{"five_hour":null,"seven_day":null}']) expect(parseUsage(t, 1)).toBe(null)
  })

  test('drops only the gauge whose fields are wrong', () => {
    const r = parseUsage(JSON.stringify({ five_hour: { utilization: '12' }, seven_day: { utilization: 44, resets_at: 7 }, limits: 'x' }), 1)
    expect(r).toEqual({ at: 1, five: null, week: { percentUsed: 44 }, fable: null })
  })

  test('finds the Fable limit by its scope, not its position', () => {
    const body = {
      seven_day: { utilization: 10 },
      limits: [
        { kind: 'weekly_scoped', percent: 90, scope: { model: { display_name: 'Opus' } } },
        { kind: 'weekly_scoped', percent: 12, scope: { model: { display_name: 'Fable' } } },
      ],
    }
    expect(parseUsage(JSON.stringify(body), 1)?.fable).toBe(12)
  })
})
