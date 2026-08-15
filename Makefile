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

# --- trimmed build ------------------------------------------------------------------
#
# Memory scales with expanded word forms, not with entries, and a full Slovak dictionary
# expands to ~2.9 M of them — too much for an editor plugin. `make trim` keeps the most
# useful entries under a budget of forms, spending it where it buys the most text:
# value = frequency of the whole paradigm, cost = number of forms it expands into.
#
# The frequency lists are a SELECTION CRITERION ONLY. Not one word from them enters the
# data — every word still comes from hunspell-sk. They are not redistributed here, so
# point the variables at your own copies:
#
#   FREQ_SNK  lemma frequency list of prim-11.0-public-all, Slovak National Corpus
#             https://korpus.juls.savba.sk/files/prim-11.0/
#   FREQ_OS   OpenSubtitles frequency list (MIT), hermitdave/FrequencyWords, sk_full.txt
#
#   make trim FREQ_SNK=../snk_lemma.txt.bz2 FREQ_OS=../sk_full.txt BUDGET=620000

BUDGET   ?= 620000
TRIM     ?= data/trimmed
FREQ_SNK ?=
FREQ_OS  ?=

.PHONY: trim

trim: $(TRIM)/dictionary.dict
	@echo "trimmed to a budget of $(BUDGET) word forms"

$(TRIM)/stem_freq.tsv: $(UPSTREAM)/sk_SK.dic $(DATA)/superlatives.tsv scripts/freq_join.py
	@test -n "$(FREQ_SNK)" || { echo "set FREQ_SNK (see the Makefile header)"; exit 1; }
	@mkdir -p $(TRIM)
	$(PYTHON) scripts/freq_join.py --dic $(UPSTREAM)/sk_SK.dic --snk $(FREQ_SNK) \
	  $(if $(FREQ_OS),--os $(FREQ_OS),) --extra $(DATA)/superlatives.tsv -o $@

$(TRIM)/costs.tsv: $(DATA)/dictionary.dict $(DATA)/annotations.json scripts/paradigm_cost.py
	@mkdir -p $(TRIM)
	$(PYTHON) scripts/paradigm_cost.py $(DATA)/dictionary.dict $(DATA)/annotations.json -o $@

$(TRIM)/keep_stems.txt: $(TRIM)/stem_freq.tsv $(TRIM)/costs.tsv scripts/plan_cut.py
	$(PYTHON) scripts/plan_cut.py --freq $(TRIM)/stem_freq.tsv --cost $(TRIM)/costs.tsv \
	  --budget $(BUDGET) -o $@ --report $(TRIM)/report.txt

$(TRIM)/dictionary.dict: $(TRIM)/keep_stems.txt $(UPSTREAM)/sk_SK.dic scripts/dic2dict.py
	$(PYTHON) scripts/dic2dict.py $(UPSTREAM)/sk_SK.dic -o $@ --source-rev "$(REV)" \
	  --keep-stems $(TRIM)/keep_stems.txt --extra-entries $(DATA)/superlatives.tsv

clean:
	rm -f $(DATA)/dictionary.dict $(DATA)/annotations.json $(DATA)/superlatives.tsv
	rm -rf $(TRIM)
