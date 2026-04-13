.PHONY: setup run test

setup:
	pip install -r requirements.txt && python -m src.db.init

run:
	caffeinate -i python -m src.bot.main

test:
	pytest tests/ -v
