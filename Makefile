SHELL := /bin/bash
.PHONY: gliner-up gliner-down gliner-tests create-gliner-variables

gliner-up:
	docker compose up -d --build gliner

gliner-down:
	docker compose stop gliner

gliner-tests:
	docker compose run --rm --no-deps \
		-v ./tests:/app/tests:ro \
		-v ./src/ro_dou_enrichment:/app/ro_dou_enrichment:ro \
		-v ./requirements-test.txt:/app/requirements-test.txt:ro \
		gliner sh -c "pip install -q --user -r requirements-test.txt && python -m pytest -q -p no:cacheprovider tests"

create-gliner-variables:
	$(MAKE) -C ../Ro-dou create-gliner-variables
