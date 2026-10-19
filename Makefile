.PHONY: setup models test demo serve budget eval help
help:
	@echo "make setup   one-time install (needs uv + ffmpeg)"
	@echo "make test    run the tests (no keys, no network)"
	@echo "make demo    rerun the pipeline on the cached Runway clips (no Runway key)"
	@echo "make serve   local site at http://127.0.0.1:8765"
	@echo "make budget  show your live Runway credit balance (needs RUNWAY_API_KEY)"

setup:
	scripts/setup.sh

models:
	scripts/fetch_models.sh

test:
	.venv/bin/python -m pytest

# cached clips in data/runs/put-the-red-block-in-the-bowl/clips; a short 300-step train and a 5-start eval keep it quick
demo:
	bin/understudy run "put the red block in the bowl" --no-generate --train-steps 300 --eval-seeds 5

serve:
	bin/understudy serve

budget:
	bin/understudy budget
