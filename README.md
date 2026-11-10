# deepseek_pricing
Indicate the schedule (start time, end time) for when Deepseek is 
in peak pricing

Pricing is evaluated in UTC, as published: weekends and Chinese public
holidays are always off-peak; on other days 01:00-04:00 and 06:00-10:00
UTC are peak.

Both commands check the DeepSeek documentation at startup. The rules
above are copied from one paragraph of the published pricing page, so
`json` and `gui` refuse to run if that paragraph is missing or has been
reworded - a change there means the local schedule has to be reviewed,
not guessed at. `--help` and a bare invocation skip the check, so the
usage text never needs the network.

The command is installed as `deepseek-alert`. It can also be run straight
from the source tree, which is what the examples below do.

## Help
```
uv run src/deepseek_pricing/__init__.py --help
```

There are two commands, `json` and `gui`. With no command at all the
help text is printed.

## JSON

```
uv run src/deepseek_pricing/__init__.py json
```

Returns the next few pricing periods. Use `--start-at` to start from a
given instant instead of the current time, and `--max-periods` to choose
how many periods come back. With a fixed timestamp the output is
reproducible, so the sample below is exactly what this prints:

```
uv run src/deepseek_pricing/__init__.py json \
    --start-at 2026-11-10T23:15:00+08:00 --max-periods 3
```

[deepseek_pricing.schema.json](src/deepseek_pricing.schema.json)
describes how the next few pricing periods are represented
in JSON.

For example:

```json
{
  "version": 1,
  "periods": [
    {
      "startTime": "2026-11-10T15:15:00+00:00",
      "endTime": "2026-11-11T01:00:00+00:00",
      "pricing": "NONPEAK"
    },
    {
      "startTime": "2026-11-11T01:00:00+00:00",
      "endTime": "2026-11-11T04:00:00+00:00",
      "pricing": "PEAK"
    },
    {
      "startTime": "2026-11-11T04:00:00+00:00",
      "endTime": "2026-11-11T06:00:00+00:00",
      "pricing": "NONPEAK"
    }
  ]
}
```

The first period starts at the current time, or at `--start-at` if it is
given, and each later period starts where the previous one ended, so the
periods are contiguous and alternate between `PEAK` and `NONPEAK`.

The `--start-at` value is an ISO 8601 timestamp and must include a UTC
offset, either numeric (`+08:00`, `-05:00`, `+0000`) or `Z` for UTC. A
timestamp with no offset, such as `2026-11-10T23:15`, is rejected:
without an offset the instant is ambiguous.

The periods are always reported in UTC, with a `+00:00` offset, because
that is the unit the peak hours are published in. An offset in
`--start-at` therefore says which instant to start from, not which offset
to print: `2026-11-10T23:15:00+08:00` and `2026-11-10T15:15:00Z` name the
same instant and produce the same output.

There are options to change the number of periods that is returned
in the JSON. See `json --help`.

```
--start-at TIMESTAMP    start at an ISO 8601 time with a UTC offset (default: now)
--max-periods N         emit at most N periods (default 5)
--max-peak-periods N    stop after N peak periods (default --max-periods)
--max-nonpeak-periods N stop after N non-peak periods (default --max-periods)
```

These options belong to the `json` command. They are not accepted by
`gui`, and giving one without a command is a usage error.

## GUI

```
uv run src/deepseek_pricing/__init__.py gui
```

Runs a GUI application that will become a full screen 
display to notify the user when a peak pricing period
is in effect, or about to start.

The GUI is only imported by the `gui` command, so `json` and `--help`
work without tkinter or a display.

`gui` needs tkinter, which some Linux distributions ship as a separate
package:

```
sudo apt install python3-tk      # Debian and Ubuntu
sudo dnf install python3-tkinter # Fedora
```
