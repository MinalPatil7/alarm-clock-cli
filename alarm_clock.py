#!/usr/bin/env python3
"""
Alarm Clock CLI
===============

A simple command-line alarm clock.

Commands:
    alarm_clock.py add HH:MM [--label TEXT] [--repeat once|daily]
    alarm_clock.py list
    alarm_clock.py remove ID
    alarm_clock.py run

Design notes (see README for the full write-up):
- Alarms persist in a local JSON file (alarms.json) — no database.
- `run` is a blocking foreground loop: it's what makes this an
  "alarm clock" rather than just a scheduler. It checks the time every
  second and rings when an enabled alarm matches.
- Ringing uses the terminal bell + a repeated banner, since audio
  playback would add OS-specific dependencies out of scope for this
  exercise.
- While ringing, the user can dismiss (Enter) or snooze (s + minutes).
- "once" alarms disable themselves after ringing; "daily" alarms
  reset to fire again the next day.
"""

import argparse
import json
import sys
import time
import itertools
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

STORE_PATH = Path(__file__).parent / "alarms.json"


@dataclass
class Alarm:
    id: int
    time: str  # "HH:MM", 24-hour
    label: str = ""
    repeat: str = "once"  # "once" | "daily"
    enabled: bool = True

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        return Alarm(**d)


class AlarmStore:
    """Handles loading/saving alarms to a local JSON file."""

    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self.alarms: list[Alarm] = []
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text())
                self.alarms = [Alarm.from_dict(a) for a in raw]
            except (json.JSONDecodeError, TypeError, KeyError):
                # Corrupt file — start fresh rather than crash.
                self.alarms = []
        else:
            self.alarms = []

    def save(self):
        self.path.write_text(
            json.dumps([a.to_dict() for a in self.alarms], indent=2)
        )

    def next_id(self) -> int:
        return max((a.id for a in self.alarms), default=0) + 1

    def add(self, time_str: str, label: str, repeat: str) -> Alarm:
        alarm = Alarm(id=self.next_id(), time=time_str, label=label, repeat=repeat)
        self.alarms.append(alarm)
        self.save()
        return alarm

    def remove(self, alarm_id: int) -> bool:
        before = len(self.alarms)
        self.alarms = [a for a in self.alarms if a.id != alarm_id]
        changed = len(self.alarms) != before
        if changed:
            self.save()
        return changed

    def get(self, alarm_id: int) -> Optional[Alarm]:
        return next((a for a in self.alarms if a.id == alarm_id), None)


def validate_time(time_str: str) -> str:
    """Validate HH:MM 24-hour format; raises argparse-friendly error."""
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"'{time_str}' is not a valid time — use 24-hour HH:MM, e.g. 07:30"
        )
    return time_str


def cmd_add(args):
    store = AlarmStore()
    alarm = store.add(args.time, args.label or "", args.repeat)
    print(f"Added alarm #{alarm.id}: {alarm.time} "
          f"({alarm.repeat}){' — ' + alarm.label if alarm.label else ''}")


def cmd_list(args):
    store = AlarmStore()
    if not store.alarms:
        print("No alarms set.")
        return
    print(f"{'ID':<4} {'TIME':<6} {'REPEAT':<7} {'STATUS':<8} LABEL")
    for a in sorted(store.alarms, key=lambda x: x.time):
        status = "on" if a.enabled else "off"
        print(f"{a.id:<4} {a.time:<6} {a.repeat:<7} {status:<8} {a.label}")


def cmd_remove(args):
    store = AlarmStore()
    if store.remove(args.id):
        print(f"Removed alarm #{args.id}.")
    else:
        print(f"No alarm with id #{args.id}.", file=sys.stderr)
        sys.exit(1)


def ring(alarm: Alarm):
    """Ring until the user dismisses or snoozes. Returns snooze minutes or None."""
    spinner = itertools.cycle("|/-\\")
    print("\a", end="", flush=True)
    print(f"\n*** ALARM: {alarm.time} {('— ' + alarm.label) if alarm.label else ''} ***")
    print("Press ENTER to dismiss, or type 's <minutes>' to snooze (default 5): ")

    # Simple blocking prompt with periodic bell — good enough for a CLI tool.
    while True:
        print("\a", end="", flush=True)
        try:
            response = input(f"[{next(spinner)}] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        if response == "":
            return None
        if response.startswith("s"):
            parts = response.split()
            minutes = 5
            if len(parts) > 1 and parts[1].isdigit():
                minutes = int(parts[1])
            return minutes
        print("Didn't catch that — press ENTER to dismiss, or 's <minutes>' to snooze.")


def cmd_run(args):
    store = AlarmStore()
    print(f"Alarm clock running. Watching {len(store.alarms)} alarm(s). Ctrl+C to stop.")
    last_checked_minute = None
    snoozes: dict[int, datetime] = {}  # alarm_id -> fire_at

    try:
        while True:
            now = datetime.now()

            # Check snoozed alarms (minute-resolution match).
            for alarm_id, fire_at in list(snoozes.items()):
                if now >= fire_at:
                    alarm = store.get(alarm_id)
                    if alarm:
                        snooze_minutes = ring(alarm)
                        if snooze_minutes:
                            snoozes[alarm_id] = datetime.now() + timedelta(minutes=snooze_minutes)
                            print(f"Snoozed for {snooze_minutes} minute(s).")
                        else:
                            del snoozes[alarm_id]
                            _post_ring_state(store, alarm)

            # Check regular alarms once per minute (avoid re-firing within the same minute).
            current_minute = now.strftime("%H:%M")
            if current_minute != last_checked_minute:
                last_checked_minute = current_minute
                store._load()  # pick up any edits made in another terminal
                for alarm in store.alarms:
                    if alarm.enabled and alarm.time == current_minute:
                        snooze_minutes = ring(alarm)
                        if snooze_minutes:
                            snoozes[alarm.id] = datetime.now() + timedelta(minutes=snooze_minutes)
                            print(f"Snoozed for {snooze_minutes} minute(s).")
                        else:
                            _post_ring_state(store, alarm)

            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping alarm clock. Goodbye.")


def _post_ring_state(store: AlarmStore, alarm: Alarm):
    """After a dismissed (non-snoozed) ring: disable 'once' alarms; leave 'daily' as-is."""
    if alarm.repeat == "once":
        alarm.enabled = False
        store.save()
    print(f"Dismissed alarm #{alarm.id}.")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="alarm_clock",
        description="A simple command-line alarm clock.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add a new alarm")
    p_add.add_argument("time", type=validate_time, help="Time in 24h HH:MM, e.g. 07:30")
    p_add.add_argument("--label", help="Optional label, e.g. 'Wake up'")
    p_add.add_argument("--repeat", choices=["once", "daily"], default="once")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="List all alarms")
    p_list.set_defaults(func=cmd_list)

    p_remove = sub.add_parser("remove", help="Remove an alarm by id")
    p_remove.add_argument("id", type=int)
    p_remove.set_defaults(func=cmd_remove)

    p_run = sub.add_parser("run", help="Start watching for alarms (foreground)")
    p_run.set_defaults(func=cmd_run)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()