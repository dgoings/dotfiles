// A trimmed real response from the usage service, 2026-11-16.
export const SAMPLE = JSON.stringify({
  five_hour: { utilization: 0.0, resets_at: '2026-11-16T20:30:00.205053+00:00' },
  seven_day: { utilization: 31.0, resets_at: '2026-11-19T21:00:00.205079+00:00' },
  seven_day_opus: null,
  limits: [
    { kind: 'session', group: 'session', percent: 0, resets_at: '2026-11-16T20:30:00.205053+00:00', scope: null, is_active: false },
    { kind: 'weekly_all', group: 'weekly', percent: 31, resets_at: '2026-11-19T21:00:00.205079+00:00', scope: null, is_active: false },
    {
      kind: 'weekly_scoped', group: 'weekly', percent: 36, resets_at: '2026-11-19T21:00:00.205257+00:00',
      scope: { model: { id: null, display_name: 'Fable' }, surface: null }, is_active: true,
    },
  ],
  weekly_scoped_shares: [{ limit_index: 2, used_percent_of_weekly: 18, allowance_percent_of_weekly: 50 }],
})
