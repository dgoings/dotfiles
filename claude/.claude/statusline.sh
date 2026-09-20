#!/usr/bin/env bash
# Claude Code status line: model + rate-limit usage (the same numbers /usage shows)
# + an estimate of the Fable share of the weekly limit.
# Receives session JSON on stdin; rate_limits fields appear after the first API
# response in a session (Pro/Max only). Docs: https://code.claude.com/docs/en/statusline
set -euo pipefail

input=$(cat)

model=$(jq -r '.model.display_name // empty' <<<"$input")
five=$(jq -r '.rate_limits.five_hour.used_percentage // empty' <<<"$input")
week=$(jq -r '.rate_limits.seven_day.used_percentage // empty' <<<"$input")
reset=$(jq -r '.rate_limits.five_hour.resets_at // empty' <<<"$input")
week_reset=$(jq -r '.rate_limits.seven_day.resets_at // empty' <<<"$input")

# Elapsed share of a rate-limit window, rendered dim as "/N%" after the usage
# figure -- the pace reference: where usage would sit if the whole allowance
# were burned evenly across the window. Usage above it is running hot; below
# it is banked room. Args: window length in seconds, resets_at epoch.
# Prints nothing when resets_at is absent (before the first API response).
pace() {
  local len=$1 resets=$2 elapsed
  [[ "$resets" =~ ^[0-9]+$ ]] || return 0
  elapsed=$(((len - (resets - $(date +%s))) * 100 / len))
  [ "$elapsed" -lt 0 ] && elapsed=0
  [ "$elapsed" -gt 100 ] && elapsed=100
  printf '\033[2m/%s%%\033[0m' "$elapsed"
}

# Colorize a used-percentage: green < 50, yellow < 80, red >= 80.
pct() {
  local n
  n=$(printf '%.0f' "$1")
  if [ "$n" -ge 80 ]; then printf '\033[31m%s%%\033[0m' "$n"
  elif [ "$n" -ge 50 ]; then printf '\033[33m%s%%\033[0m' "$n"
  else printf '\033[32m%s%%\033[0m' "$n"
  fi
}

# Fable weekly usage, as an estimated percentage of the plan's Fable sub-limit.
# /usage shows this as a third bar ("Current week (Fable)") but rate_limits
# carries no per-model buckets, so it is reconstructed here.
#
# Cost, not token count, is the basis. Raw input+output is under 1% of the
# tokens actually metered — cache reads outnumber it ~100:1 — so a token-based
# estimate tracks nothing useful.
#
# The estimate is a *ratio*, not a dollar budget. Local transcripts give Fable
# spend and all-model spend since the weekly reset; the API reports the exact
# all-model percentage. So:
#
#   fable% = 7d% x (fable spend / all spend) / FABLE_SHARE
#
# The dollar amounts cancel, which is the point: the weekly allowance is never
# hardcoded, so a plan change, a limits promo, or a price change recalibrates
# on the next render instead of silently drifting. Only the *ratio* of Fable
# to non-Fable spend has to be right, and only the sub-limit fraction below is
# a fixed assumption.
#
# Counting only local transcripts still biases this, but far less than a fixed
# budget did: usage from another device is missing from both the numerator and
# the denominator, so a machine used similarly for Fable and non-Fable work
# largely cancels its own bias out. A machine used lopsidedly does not -- and
# this one is (heavier on Fable than the account overall), so the residual
# bias is folded into the constant below rather than modeled.
#
# FABLE_SHARE is the Fable sub-limit as a fraction of the plan's weekly
# allowance. It is plan-level and committed (this script is stowed across
# machines), which rests on one assumption: the Fable/non-Fable usage mix is
# roughly similar across this account's machines. The /usage percentages are
# account-global; the transcript scan is local to one machine. A machine
# whose mix is persistently lopsided vs the account's will render a skewed
# estimate that no shared constant can correct.
#
# Calibration recipe -- compare against /usage while the 7d bar itself is
# accurate, then:
#
#   new = current x (rendered fable % / usage fable %)
#
# Recalibrate after a plan change or limits promo change, and prefer readings
# late in the weekly window: /usage rounds to whole percents, so small bars
# make the correction factor noisy.
#
# Calibration log ($200 Max plan; promo status unverified):
#   2026-08-08  Four readings that day implied a share near 1.0, i.e. the
#               Fable bar sharing the weekly allowance outright. All four are
#               void: the scan was summing duplicate rows (see the dedup note
#               in the awk below), and the duplication was heavier on Fable
#               than on the rest, so the local ratio was inflated by a factor
#               that drifted with how often sessions were resumed. Every
#               constant fitted before the dedup fix encodes that drift.
#   2026-08-11  First reading after deduplicating: 7d 44%, Fable 36%, local
#               ratio 0.327 -> implied 0.40 (rounding bounds 0.39-0.41).
#               The bars were large enough that rounding leaves little slack,
#               so this is the first calibration worth trusting. Note the
#               local ratio (0.327) and the bar ratio (36/44 = 0.818) are far
#               apart, which is the sub-limit doing real work -- the earlier
#               "shared allowance" conclusion was an artifact of the bug.
FABLE_SHARE=0.40 # Fable sub-limit as a fraction of the weekly allowance

# Start of the current weekly window. Preferred source is the reset timestamp
# the API itself reports, so the local scan covers the same span as the 7d
# percentage it is scaled against. Falls back to the local calendar (Thursday
# 5pm) when rate_limits is absent -- derived from the calendar rather than by
# subtracting 604800 seconds, so a DST change doesn't walk the boundary an
# hour off.
if [[ "$week_reset" =~ ^[0-9]+$ ]]; then
  window_epoch=$((week_reset - 604800))
else
  days_back=$((($(date +%u) - 4 + 7) % 7)) # 4 = Thursday, matching `date +%u`
  if [ "$days_back" -eq 0 ] && [ "$((10#$(date +%H)))" -lt 17 ]; then
    days_back=7
  fi
  window_epoch=$(date -j -f '%Y-%m-%d %H:%M:%S' \
    "$(printf '%s 17:00:00' "$(date -v-${days_back}d +%F)")" +%s)
fi
window_start=$(date -r "$window_epoch" '+%Y-%m-%d %H:%M:%S')

cache="${TMPDIR:-/tmp}/claude-statusline-fable.$(id -u)"
fable_cost=""
all_cost=""

# Cache line is "<epoch> <window> <fable cost> <all cost>"; reuse while
# same-window and fresh. A short line is a pre-ratio cache -- treat as stale.
if [ -r "$cache" ]; then
  read -r cached_at cached_window cached_fable cached_all <"$cache" 2>/dev/null || true
  if [[ ${cached_at:-} =~ ^[0-9]+$ ]] && [ "${cached_window:-}" = "$window_epoch" ] &&
    [ -n "${cached_all:-}" ] && [ $(($(date +%s) - cached_at)) -lt 120 ]; then
    fable_cost=$cached_fable
    all_cost=$cached_all
  fi
fi

if [ -z "$all_cost" ]; then
  transcripts=()
  while IFS= read -r -d '' t; do transcripts+=("$t"); done < <(
    find "$HOME/.claude/projects" -name '*.jsonl' -newermt "$window_start" -print0 2>/dev/null
  )

  fable_cost=0
  all_cost=0
  if [ ${#transcripts[@]} -gt 0 ]; then
    # Read as raw lines and parse each individually: a transcript truncated
    # mid-write leaves a partial final line, and letting jq parse the file as
    # JSON would abort the whole scan on it and silently report zero.
    #
    # Timestamps are UTC with fractional seconds, which fromdateiso8601 rejects
    # outright, so strip the fraction before comparing against the window.
    # Subagent transcripts live in subagents/ subdirectories and are counted too
    # — they are a large share of real usage.
    read -r fable_cost all_cost < <(jq -rR --argjson since "$window_epoch" '
      fromjson?
      | objects
      | select(.type == "assistant")
      | select((.timestamp // "") | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601? // 0 | . >= $since)
      | (.message.usage // {}) as $u
      | [ (.message.id // "?"), (.message.model // "unknown"),
          ($u.input_tokens // 0), ($u.output_tokens // 0), ($u.cache_read_input_tokens // 0),
          ($u.cache_creation.ephemeral_5m_input_tokens // 0),
          ($u.cache_creation.ephemeral_1h_input_tokens // 0) ] | @tsv
    ' "${transcripts[@]}" 2>/dev/null |
      # List rates per MTok, by family: input, output, cache read, 5m cache
      # write, 1h cache write. Cache read is 0.1x input, 5m write 1.25x, 1h
      # write 2x. Unrecognized models are priced as Opus, the common case.
      awk -F'\t' '
        function family(m) {
          if (m ~ /^claude-(fable|mythos)/) return "fable"
          if (m ~ /^claude-sonnet/) return "sonnet"
          if (m ~ /^claude-haiku/) return "haiku"
          return "opus"
        }
        BEGIN {
          i["fable"]=10;  o["fable"]=50;  r["fable"]=1;    w5["fable"]=12.5; w1["fable"]=20
          i["opus"]=5;    o["opus"]=25;   r["opus"]=0.5;   w5["opus"]=6.25;  w1["opus"]=10
          i["sonnet"]=3;  o["sonnet"]=15; r["sonnet"]=0.3; w5["sonnet"]=3.75; w1["sonnet"]=6
          i["haiku"]=1;   o["haiku"]=5;   r["haiku"]=0.1;  w5["haiku"]=1.25; w1["haiku"]=2
        }
        # One API response can appear many times: streaming writes a row per
        # progress snapshot, and resuming or forking a session copies the whole
        # transcript into a new file. Both share .message.id, so key on it.
        #
        # Snapshots of one response repeat identical input and cache counts
        # while output_tokens grows, so summing rows inflates cache reads (the
        # dominant term) by the row count and counts partial output repeatedly.
        # Take input and cache once; take the largest output, which is the
        # final value the response settled on.
        { id = $1
          if (!(id in seen)) {
            seen[id] = 1; fam[id] = family($2)
            ti[id] = $3; to[id] = $4; tr[id] = $5; t5[id] = $6; t1[id] = $7
          } else if ($4 + 0 > to[id] + 0) to[id] = $4 }
        # Trailing newline matters: `read` reports failure on an unterminated
        # line even after assigning, which would zero both costs below.
        END {
          for (id in seen) {
            f = fam[id]
            c = (ti[id]*i[f] + to[id]*o[f] + tr[id]*r[f] + t5[id]*w5[f] + t1[id]*w1[f]) / 1e6
            all += c; if (f == "fable") fab += c
          }
          printf "%.4f %.4f\n", fab, all
        }') || { fable_cost=0; all_cost=0; }
  fi
  # stderr is redirected first so a failed open on $cache stays quiet too;
  # bash applies redirections left to right and reports the failure itself.
  printf '%s %s %s %s\n' "$(date +%s)" "$window_epoch" "$fable_cost" "$all_cost" \
    2>/dev/null >"$cache" || true
fi

# Needs the reported 7d percentage to scale against, so the Fable segment is
# absent until the session's first API response populates rate_limits.
fable=0
if [[ "$week" =~ ^[0-9.]+$ ]]; then
  fable=$(awk -v w="$week" -v f="$fable_cost" -v a="$all_cost" -v s="$FABLE_SHARE" \
    'BEGIN { if (a > 0 && s > 0) printf "%.0f", w * (f / a) / s; else print 0 }' 2>/dev/null) || fable=0
fi

out="${model:-Claude}"
[ -n "$five" ] && out+=" | 5h $(pct "$five")$(pace 18000 "$reset")"
if [[ "$reset" =~ ^[0-9]+$ ]]; then
  out+=" (resets $(date -r "$reset" +%H:%M))"
fi
# The Fable bar shares the 7d window, so this pace reference covers it too.
[ -n "$week" ] && out+=" | 7d $(pct "$week")$(pace 604800 "$week_reset")"
# Tilde marks this as a local estimate, not a figure the API reported.
case $fable in
'' | 0 | *[!0-9]*) ;;
*) out+=" | Fable ~$(pct "$fable")" ;;
esac

printf '%s\n' "$out"
