# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Branislav Klocok
#
# Rebuild the Slovak Harper dictionary data from sk-spell/hunspell-sk.
#
#   make fetch    clone or update the hunspell-sk source
#   make build    regenerate data/dictionary.dict and data/annotations.json
#   make          fetch + build
#
# To build against an existing checkout instead of cloning:
#   make build UPSTREAM=../hunspell-sk

HUNSPELL_SK_URL ?= https://github.com/sk-spell/hunspell-sk.git
UPSTREAM        ?= upstream/hunspell-sk
DATA            ?= data
PYTHON          ?= python3

REV = $(shell git -C $(UPSTREAM) log -1 --format='%h (%ad)' --date=short 2>/dev/null || echo unknown)

.PHONY: all fetch build clean

all: fetch build

fetch:
	@if [ -d "$(UPSTREAM)/.git" ]; then \
	  echo "updating $(UPSTREAM)"; git -C "$(UPSTREAM)" pull --ff-only; \
	else \
	  echo "cloning into $(UPSTREAM)"; git clone "$(HUNSPELL_SK_URL)" "$(UPSTREAM)"; \
	fi

build: $(DATA)/dictionary.dict $(DATA)/annotations.json
	@echo "built from hunspell-sk $(REV)"

# Superlatives have to be materialised: `naj-` is licensed through hunspell continuation
# flags, which Harper's annotation format cannot express. See scripts/gen_superlatives.py.
$(DATA)/superlatives.tsv: $(UPSTREAM)/sk_SK.aff $(UPSTREAM)/sk_SK.dic scripts/gen_superlatives.py
	$(PYTHON) scripts/gen_superlatives.py $(UPSTREAM)/sk_SK.aff $(UPSTREAM)/sk_SK.dic -o $@

$(DATA)/dictionary.dict: $(UPSTREAM)/sk_SK.dic scripts/dic2dict.py $(DATA)/superlatives.tsv
	$(PYTHON) scripts/dic2dict.py $(UPSTREAM)/sk_SK.dic -o $@ --source-rev "$(REV)" \
	  --extra-entries $(DATA)/superlatives.tsv

$(DATA)/annotations.json: $(UPSTREAM)/sk_SK.aff scripts/aff2annotations.py
	$(PYTHON) scripts/aff2annotations.py $(UPSTREAM)/sk_SK.aff -o $@ --source-rev "$(REV)"

clean:
	rm -f $(DATA)/dictionary.dict $(DATA)/annotations.json $(DATA)/superlatives.tsv
