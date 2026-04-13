.PHONY: setup run test

setup:
	bash setup.sh

run:
	caffeinate -i .venv/bin/python -m src.bot.main

test:
	.venv/bin/python -m pytest tests/ -v
