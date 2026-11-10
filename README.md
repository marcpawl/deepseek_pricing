# deepseek_pricing
Indicate the schedule (start time, end time) for when Deepseek is 
in peak pricing

Pricing is evaluated in Beijing time. Weekends and Chinese public
holidays are always off-peak; on other days 01:00-04:00 and 06:00-10:00
Beijing time are peak.

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

Returns the next few pricing periods.

[deepseek_pricing.schema.json](src/deepseek_pricing.schema.json)
describes how the next few pricing periods are represented
in JSON.

For example:

```json
{
  "version": 1,
  "periods": [
    {
      "startTime": "2026-11-10T23:15:00+08:00",
      "endTime": "2026-11-11T01:00:00+08:00",
      "pricing": "NONPEAK"
    },
    {
      "startTime": "2026-11-11T01:00:00+08:00",
      "endTime": "2026-11-11T04:00:00+08:00",
      "pricing": "PEAK"
    },
    {
      "startTime": "2026-11-11T04:00:00+08:00",
      "endTime": "2026-11-11T06:00:00+08:00",
      "pricing": "NONPEAK"
    }
  ]
}
```

The first period starts at the current time, and each later period
starts where the previous one ended, so the periods are contiguous and
alternate between `PEAK` and `NONPEAK`.

Use `--start-at` to start somewhere else instead of now:

```
uv run src/deepseek_pricing/__init__.py json \
    --start-at 2026-11-10T23:15:00+08:00 --max-periods 3
```

The value is an ISO 8601 timestamp and must include a UTC offset, either
numeric (`+08:00`, `-05:00`, `+0000`) or `Z` for UTC. A timestamp with no
offset, such as `2026-11-10T23:15`, is rejected: without an offset the
instant is ambiguous.

The periods are reported in the offset that was given, so a `Z` timestamp
yields `+00:00` timestamps. This also makes the sample output above
reproducible - that is exactly how it was generated.

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
