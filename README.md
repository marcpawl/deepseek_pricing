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

With no option at all the help text is printed.

## JSON

```
uv run src/deepseek_pricing/__init__.py --json
```

Returns the next few pricing periods.

[deepseek_pricing.schema.json](src/deepseek_pricing.schema.json)
describes how the next few pricing periods are represented
in JSON.

There are options to change the number of periods that is returned
in the JSON. See help.

```
--max-periods N         emit at most N periods (default 5)
--max-peak-periods N    stop after N peak periods (default --max-periods)
--max-nonpeak-periods N stop after N non-peak periods (default --max-periods)
```

## GUI

```
uv run src/deepseek_pricing/__init__.py --gui
```

Runs a GUI application that will become a full screen 
display to notify the user when a peak pricing period
is in effect, or about to start.

`--gui` and `--json` are mutually exclusive.

The GUI is only imported when `--gui` is given, so `--json` and `--help`
work without tkinter or a display.
