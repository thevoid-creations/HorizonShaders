# Horizon Aurora: checks, packaging, documentation checks.
#
# `HORIZON` is a checkout of https://github.com/horizon-rust/horizon. With it,
# the sky and material stages are validated in the runtime modules the game
# really builds (its own terrain.wgsl spliced in); without it, those two checks
# are skipped and the rest still runs.

HORIZON    ?= ../horizon
PACKS      := packs/Horizon-Aurora packs/Horizon-Aurora-Lite
PY         ?= python3
DIST       := dist

.PHONY: all check self-test look dist clean print-hashes

all: check look

## The full check: manifest, package, every stage in naga, the runtime modules,
## and translation for Vulkan, Metal and DirectX 12.
check:
	@if [ -d "$(HORIZON)" ]; then \
		$(PY) tools/validate_pack.py check $(PACKS) --translate --horizon $(HORIZON); \
	else \
		echo "note: no Horizon checkout at $(HORIZON); skipping the runtime-module checks"; \
		$(PY) tools/validate_pack.py check $(PACKS) --translate; \
	fi

## The harness against Horizon's own known-good packs, its published Frame
## layout and a set of packs that must be refused.
self-test:
	@$(PY) tools/validate_pack.py self-test $(if $(wildcard $(HORIZON)),--horizon $(HORIZON),)

## The look, computed from the pack's own maths.
look:
	@$(PY) tools/simulate_look.py

## The constants the pack is tuned with.
values:
	@$(PY) tools/simulate_look.py --values

## .hshader files (reproducible: the same pack always gives the same bytes and
## the same SHA-256), the source archive, and their sums.
dist:
	@mkdir -p $(DIST)
	@for pack in $(PACKS); do \
		$(PY) tools/validate_pack.py pack $$pack --out $(DIST)/$$(basename $$pack).hshader --horizon $(HORIZON); \
	done
	@rm -f $(DIST)/Horizon-Aurora-Source.zip
	@cd $(DIST)/.. && zip -qr $(DIST)/Horizon-Aurora-Source.zip \
		packs docs tools README.md LICENSE Makefile .gitignore -x '*/node_modules/*' -x '*__pycache__*' -x '*.pyc' \
		-x '*.DS_Store'
	@cd $(DIST) && sha256sum *.hshader Horizon-Aurora-Source.zip > SHA256SUMS && cat SHA256SUMS

clean:
	@rm -rf $(DIST) tools/node_modules
