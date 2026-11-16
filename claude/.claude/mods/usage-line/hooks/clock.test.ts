import { describe, expect, test } from 'claude-code/testing'

import { clockBody, renderClock } from './clock'

const at = (pixels: number[], x: number, y: number) => pixels[y * 52 + x]

const BASE = { five: { percent: 24, pace: 60 }, week: { percent: 44, pace: 50 }, fable: 36 }

describe('renderClock', () => {
  test('is always 832 pixels', () => {
    expect(renderClock(BASE).length).toBe(832)
    expect(renderClock({ five: null, week: null, fable: null }).every(p => p === 0)).toBe(true)
  })

  test('draws labels grey and percentages in the tier colour', () => {
    const p = renderClock(BASE)
    expect(at(p, 0, 0)).toBe(0x8a8a8a) // top-left of "5"
    expect(at(p, 12, 0)).toBe(0x00d060) // top-left of "2" in 24%
    expect(at(p, 27, 0)).toBe(0x8a8a8a) // top-left of "7"
    expect(at(p, 0, 11)).toBe(0x8a8a8a) // top-left of "F"
    expect(at(p, 12, 12)).toBe(0x00d060) // the Fable tilde takes the tier colour
  })

  test('fills each bar by percent and marks the pace in white', () => {
    const p = renderClock(BASE)
    for (const y of [6, 7, 8]) {
      expect(at(p, 5, y)).toBe(0x00d060) // 24% of 25 cells = 6 filled
      expect(at(p, 6, y)).toBe(0x262626)
      expect(at(p, 15, y)).toBe(0xffffff) // pace 60 -> cell 15
      expect(at(p, 37, y)).toBe(0x00d060) // 44% of 25 = 11 filled, from x=27
      expect(at(p, 38, y)).toBe(0x262626)
      expect(at(p, 39, y)).toBe(0xffffff) // pace 50 -> cell 12
      expect(at(p, 25, y)).toBe(0) // the gap between the bars
      expect(at(p, 26, y)).toBe(0)
    }
    expect(at(p, 51, 6)).toBe(0x262626) // the 7D bar reaches the right edge
  })

  test('draws the Fable bar after its text, with no pace mark', () => {
    const p = renderClock(BASE)
    for (const y of [12, 13, 14]) {
      expect(at(p, 28, y)).toBe(0) // one blank column after "FB ~36%"
      expect(at(p, 36, y)).toBe(0x00d060) // 36% of 23 cells = 8 filled, from x=29
      expect(at(p, 37, y)).toBe(0x262626)
      expect(at(p, 51, y)).toBe(0x262626)
    }
    expect(at(p, 29, 11)).toBe(0)
    expect(at(p, 29, 15)).toBe(0)
    expect(p.filter(c => c === 0xffffff).length).toBe(6) // two pace marks, three rows each
  })

  test('colours by tier at 50 and 80', () => {
    expect(at(renderClock({ ...BASE, five: { percent: 49, pace: null } }), 0, 6)).toBe(0x00d060)
    expect(at(renderClock({ ...BASE, five: { percent: 50, pace: null } }), 0, 6)).toBe(0xf0b000)
    expect(at(renderClock({ ...BASE, five: { percent: 80, pace: null } }), 0, 6)).toBe(0xff3030)
  })

  test('drops the space at 100% so the text stays in its half', () => {
    const p = renderClock({ ...BASE, five: { percent: 100, pace: null } })
    expect(at(p, 9, 0)).toBe(0xff3030) // the "1" sits where the space was
    for (let y = 0; y < 5; y++) for (const x of [23, 24, 25, 26]) expect(at(p, x, y)).toBe(0)
    expect(at(p, 24, 6)).toBe(0xff3030) // full bar
  })

  test('leaves a gauge with no reading blank', () => {
    const p = renderClock({ five: null, week: { percent: 44, pace: 50 }, fable: null })
    for (let y = 0; y < 16; y++) for (let x = 0; x < 27; x++) if (y < 10) expect(at(p, x, y)).toBe(0)
    for (let y = 10; y < 16; y++) for (let x = 0; x < 52; x++) expect(at(p, x, y)).toBe(0)
    expect(at(p, 27, 0)).toBe(0x8a8a8a)
  })

  test('clamps readings outside 0..100', () => {
    const over = renderClock({ ...BASE, five: { percent: 140, pace: 250 } })
    expect(over).toEqual(renderClock({ ...BASE, five: { percent: 100, pace: 100 } }))
    const under = renderClock({ ...BASE, five: { percent: -5, pace: -10 } })
    expect(under).toEqual(renderClock({ ...BASE, five: { percent: 0, pace: 0 } }))
    expect(renderClock({ ...BASE, five: { percent: NaN, pace: null } }).length).toBe(832)
  })

  test('draws an exact Fable figure without the tilde, the bar starting closer', () => {
    const p = renderClock({ ...BASE, isFableExact: true })
    for (const y of [12, 13, 14]) {
      expect(at(p, 24, y)).toBe(0) // one blank column after "FB 36%", 6 characters, 24 px
      expect(at(p, 25, y)).toBe(0x00d060) // 36% of 27 cells = 10 filled, x=25..34
      expect(at(p, 34, y)).toBe(0x00d060)
      expect(at(p, 35, y)).toBe(0x262626)
      expect(at(p, 51, y)).toBe(0x262626)
    }
    expect(at(p, 12, 11)).toBe(0x00d060) // the top of the "3" now sits where the tilde was
  })

  test('draws the estimate as before without the flag', () => {
    expect(renderClock({ ...BASE, isFableExact: false })).toEqual(renderClock(BASE))
    const p = renderClock(BASE)
    for (const y of [12, 13, 14]) expect(at(p, 28, y)).toBe(0)
  })

  test('fits an exact Fable figure of 100 and over', () => {
    for (const fable of [100, 112]) {
      const p = renderClock({ ...BASE, fable, isFableExact: true })
      for (const y of [12, 13, 14]) {
        expect(at(p, 28, y)).toBe(0) // "FB 112%" is 7 characters, 28 px
        expect(at(p, 29, y)).toBe(0xff3030) // full bar from x=29
        expect(at(p, 51, y)).toBe(0xff3030)
      }
    }
  })

  test('fits a Fable estimate over 100', () => {
    const p = renderClock({ ...BASE, fable: 112 })
    expect(p.length).toBe(832)
    for (const y of [12, 13, 14]) {
      expect(at(p, 32, y)).toBe(0) // "FB ~112%" is 8 characters, 32 px
      expect(at(p, 33, y)).toBe(0xff3030) // full bar from x=33
      expect(at(p, 51, y)).toBe(0xff3030)
    }
  })
})

describe('clockBody', () => {
  test('wraps the pixels as a custom-app frame', () => {
    const body = JSON.parse(clockBody(renderClock(BASE), 180))
    expect(body.duration).toBe(180)
    expect(body.draw[0].db.slice(0, 4)).toEqual([0, 0, 52, 16])
    expect(body.draw[0].db[4].length).toBe(832)
  })
})
