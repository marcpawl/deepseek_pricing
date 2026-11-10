#!/bin/bash -ex
cd $(dirname $0)

# Wait a bit to allow the windowing environment
# start up
sleep 10

uv run src/deepseek_pricing/__init__.py --gui
