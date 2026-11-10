# deepseek_pricing
Indicate the schedule (start time, end time) for when Deepseek is 
in peak pricing

## Help
```
uv run src/deepseek_pricing/__init__.py --help
```

## JSON

```
uv run src/deepseek_pricing/__init__.py --json
```

Returns the next few pricing periods.

(deepseek_pricing.schema.json)[src/deepseek_pricing.schema.json]
describes how the next few pricing periods are represented
in JSON.

There are options to change the number of periods that is returned
in the JSON. See help.

## GUI

```
uv run src/deepseek_pricing/__init__.py --gui
```

Runs a GUI application that will become a full screen 
display to notify the user when a peak pricing period
is in effect, or about to start.
