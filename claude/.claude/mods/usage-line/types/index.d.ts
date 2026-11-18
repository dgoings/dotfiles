export type RateWindow = { kind: string; percentUsed: number; resetsAt?: string }

/** The Fable scan's result: dollar spend by Fable and by every model since the weekly window opened. */
export type Spend = { fable: number; all: number }

/** One rate-limit window as the usage service reports it. */
export type ServiceWindow = { percentUsed: number; resetsAt?: string }

/** The usage service's answer, read at `at` (epoch ms); a gauge the answer did not carry is null. */
export type ServiceReading = { at: number; five: ServiceWindow | null; week: ServiceWindow | null; fable: number | null }

/** The kinds of rate-limit window the sessions share: the 5-hour and the 7-day. */
export type ReadingKind = 'five_hour' | 'seven_day'

/**
 * One window as a session read it, and when (epoch ms): `session.measure` stamps the time
 * it fired; a reading from `session.start` is of unknown age and is stamped 0.
 */
export type SharedReading = { at: number; percentUsed: number; resetsAt?: string }

/** The newest reading of each window any session has seen, shared through the store. */
export type SharedReadings = Partial<Record<ReadingKind, SharedReading>>

export type Snapshot = {
  model: string
  spend: Spend | null
  /** Milliseconds since the epoch at the last tick or push: the pace references and reset clocks read it. */
  now: number
  /** The usage service's last reading, shared between sessions through the store; null before one. */
  service: ServiceReading | null
  /** The sessions' shared readings, copied from the store before each push; null before the first copy. */
  readings: SharedReadings | null
}

declare module 'claude-code' {
  interface PluginState {
    'usage-line': { snapshot: Snapshot | null }
  }
}
