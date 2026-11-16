import { tier } from './usage'

export const CLOCK_W = 52
export const CLOCK_H = 16

export type ClockGauge = { percent: number; pace: number | null }
/** `isFableExact` marks a Fable figure the usage service reported; without it the row carries the estimate's tilde. */
export type ClockFigures = { five: ClockGauge | null; week: ClockGauge | null; fable: number | null; isFableExact?: boolean }

const TIER_COLOR = { success: 0x00d060, warning: 0xf0b000, error: 0xff3030 } as const
const EMPTY = 0x262626
const PACE = 0xffffff
const LABEL = 0x8a8a8a

/** 3x5 glyphs, rows top to bottom, `X` lit. */
const GLYPHS: Record<string, string[]> = {
  '0': ['XXX', 'X.X', 'X.X', 'X.X', 'XXX'],
  '1': ['.X.', 'XX.', '.X.', '.X.', 'XXX'],
  '2': ['XXX', '..X', 'XXX', 'X..', 'XXX'],
  '3': ['XXX', '..X', 'XXX', '..X', 'XXX'],
  '4': ['X.X', 'X.X', 'XXX', '..X', '..X'],
  '5': ['XXX', 'X..', 'XXX', '..X', 'XXX'],
  '6': ['XXX', 'X..', 'XXX', 'X.X', 'XXX'],
  '7': ['XXX', '..X', '..X', '.X.', '.X.'],
  '8': ['XXX', 'X.X', 'XXX', 'X.X', 'XXX'],
  '9': ['XXX', 'X.X', 'XXX', '..X', 'XXX'],
  H: ['X.X', 'X.X', 'XXX', 'X.X', 'X.X'],
  D: ['XX.', 'X.X', 'X.X', 'X.X', 'XX.'],
  F: ['XXX', 'X..', 'XX.', 'X..', 'X..'],
  B: ['XX.', 'X.X', 'XX.', 'X.X', 'XX.'],
  '%': ['X.X', '..X', '.X.', 'X..', 'X.X'],
  '~': ['...', 'XX.', '.XX', '...', '...'],
}

const ADVANCE = 4
const HALF_X = 27
const HALF_CELLS = 25

const clamp = (n: number, hi: number) => Math.min(hi, Math.max(0, n))
/** Whole-number reading in 0..hi; NaN counts as 0. */
const reading = (n: number, hi: number) => (Number.isNaN(n) ? 0 : clamp(Math.round(n), hi))

const setPixel = (pixels: number[], x: number, y: number, color: number) => {
  if (x >= 0 && x < CLOCK_W && y >= 0 && y < CLOCK_H) pixels[y * CLOCK_W + x] = color
}

/** Draws `text` with its top-left at (x, y); returns the x after its last advance. */
const drawText = (pixels: number[], x: number, y: number, text: string, color: number): number => {
  for (const ch of text) {
    GLYPHS[ch]?.forEach((row, dy) => {
      for (let dx = 0; dx < 3; dx++) if (row[dx] === 'X') setPixel(pixels, x + dx, y + dy, color)
    })
    x += ADVANCE
  }
  return x
}

/** A bar of `cells` cells, three rows tall from `y`, filled like `meter()` in usage.ts. */
const drawBar = (
  pixels: number[], x: number, y: number, cells: number, percent: number, pace: number | null, color: number,
) => {
  const filled = clamp(Math.round((percent / 100) * cells), cells)
  const tick = pace === null ? -1 : clamp(Math.floor((pace / 100) * cells), cells - 1)
  for (let i = 0; i < cells; i++) {
    const c = i === tick ? PACE : i < filled ? color : EMPTY
    for (let dy = 0; dy < 3; dy++) setPixel(pixels, x + i, y + dy, c)
  }
}

const drawGauge = (pixels: number[], x: number, name: string, gauge: ClockGauge) => {
  const percent = reading(gauge.percent, 100)
  const color = TIER_COLOR[tier(percent)]
  const at = drawText(pixels, x, 0, percent === 100 ? name : `${name} `, LABEL)
  drawText(pixels, at, 0, `${percent}%`, color)
  const pace = gauge.pace === null ? null : clamp(Number.isNaN(gauge.pace) ? 0 : gauge.pace, 100)
  drawBar(pixels, x, 6, HALF_CELLS, percent, pace, color)
}

/** The gauges as a 52x16 frame: 832 pixels, row-major, each 0x00RRGGBB. */
export const renderClock = (figures: ClockFigures): number[] => {
  const pixels = new Array<number>(CLOCK_W * CLOCK_H).fill(0)
  if (figures.five !== null) drawGauge(pixels, 0, '5H', figures.five)
  if (figures.week !== null) drawGauge(pixels, HALF_X, '7D', figures.week)
  if (figures.fable !== null) {
    const percent = reading(figures.fable, 999)
    const color = TIER_COLOR[tier(percent)]
    const at = drawText(pixels, 0, 11, 'FB ', LABEL)
    const end = drawText(pixels, at, 11, `${figures.isFableExact ? '' : '~'}${percent}%`, color)
    const barX = end + 1
    drawBar(pixels, barX, 12, CLOCK_W - barX, Math.min(percent, 100), null, color)
  }
  return pixels
}

/** The JSON request body that shows `pixels` as a custom-app frame for `durationSec` seconds. */
export const clockBody = (pixels: number[], durationSec: number): string =>
  JSON.stringify({ duration: durationSec, draw: [{ db: [0, 0, CLOCK_W, CLOCK_H, pixels] }] })
