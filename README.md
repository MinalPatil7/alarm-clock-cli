# Alarm Clock CLI

A command-line alarm clock built in Python (standard library only).

## Why it's built this way

The brief was intentionally open-ended ("build an alarm clock, CLI only,
no spec"). Before writing code, I used AI-assisted brainstorming to turn
that into a concrete, time-boxed scope:

**In scope**
- Multiple alarms, each with a time (`HH:MM`, 24h), optional label, and
  repeat mode (`once` or `daily`).
- Persistence across runs via a local `alarms.json` file — no database,
  per the brief.
- A foreground `run` command that actively watches the clock and rings
  when an alarm's time arrives. This is the part that makes it an
  *alarm clock* rather than just a to-do list with times attached.
- Dismiss / snooze interaction while an alarm is ringing.

**Explicitly out of scope** (documented trade-offs, not oversights):
- No GUI — CLI only, as required.
- No real audio playback — uses the terminal bell (`\a`) plus a
  repeated visual banner, to avoid pulling in OS-specific audio
  dependencies for a short exercise.
- No timezone handling — uses local system time.
- No multi-user / concurrent-process locking — single user, single
  terminal is assumed.

## Design

- `Alarm` — dataclass: `id`, `time`, `label`, `repeat`, `enabled`.
- `AlarmStore` — loads/saves the alarm list to `alarms.json`, and
  provides `add` / `remove` / `get`.
- CLI — `argparse` with subcommands (`add`, `list`, `remove`, `run`).
- `run` — loops once per second, checks the current time against
  enabled alarms once per minute (to avoid re-firing within the same
  minute), and calls `ring()` on a match. `ring()` blocks with a
  prompt: Enter to dismiss, or `s <minutes>` to snooze. `once` alarms
  disable themselves after a non-snoozed dismissal; `daily` alarms
  stay enabled for the next day.

## Usage

```bash
# Add an alarm
python3 alarm_clock.py add 07:30 --label "Wake up" --repeat daily

# Add a one-off alarm (default repeat = once)
python3 alarm_clock.py add 09:00 --label "Standup"

# List alarms
python3 alarm_clock.py list

# Remove an alarm by id
python3 alarm_clock.py remove 2

# Start the alarm clock (foreground; Ctrl+C to stop)
python3 alarm_clock.py run
```

While an alarm is ringing:
- Press **Enter** to dismiss.
- Type `s` or `s 10` to snooze (default 5 minutes, or specify minutes).

## Testing performed

- Manual smoke test of `add` / `list` / `remove` (see commands above).
- Time-format validation checked for both a valid (`07:30`) and invalid
  (`25:99`) input to confirm `argparse` rejects bad input with a clear
  message.
- `run` loop logic reviewed by inspection: minute-resolution check
  prevents double-firing within the same minute; snooze tracked
  separately per alarm id so multiple alarms can be snoozed
  independently.

## Possible next steps (not built, due to time-box)

- Real audio playback (e.g. via `playsound`, behind an optional flag).
- Config for alarm sound file.
- `--dry-run` / accelerated clock for automated testing of `run`.
- Unit tests with `pytest` mocking `datetime.now()`.

## Requirements

Python 3.9+, standard library only — no external dependencies.