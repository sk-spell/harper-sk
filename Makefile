# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Branislav Klocok
#
# Rebuild the Slovak Harper dictionary data from sk-spell/hunspell-sk.
#
#   make fetch    clone or update the hunspell-sk source
#   make build    regenerate data/dictionary.dict and data/annotations.json
#   make retrim   regenerate data/trimmed/dictionary.dict from the committed keep list
#   make          fetch + build
#
# To build against an existing checkout instead of cloning:
#   make build UPSTREAM=../hunspell-sk

HUNSPELL_SK_URL ?= https://github.com/sk-spell/hunspell-sk.git
UPSTREAM        ?= upstream/hunspell-sk
DATA            ?= data
PYTHON          ?= python3
# Carry case/number/gender/person from the affix rules into Harper (see
# scripts/aff2annotations.py): none | verbs | full. `full` needs Harper support
# for the extra cases, animacy and adjectives (Dronakurl/harper#11).
MORPHOLOGY      ?= none
MORPH_ARGS       = --morphology $(MORPHOLOGY) --aff $(UPSTREAM)/sk_SK.aff

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
	  --extra-entries $(DATA)/superlatives.tsv $(MORPH_ARGS)

$(DATA)/annotations.json: $(UPSTREAM)/sk_SK.aff scripts/aff2annotations.py
	$(PYTHON) scripts/aff2annotations.py $(UPSTREAM)/sk_SK.aff -o $@ --source-rev "$(REV)" \
	  --morphology $(MORPHOLOGY)

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

.PHONY: trim retrim

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
	  --keep-stems $(TRIM)/keep_stems.txt --extra-entries $(DATA)/superlatives.tsv $(MORPH_ARGS)

# `make retrim` applies the committed selection (keep_stems.txt) to the current source and
# needs no frequency lists, so the weekly rebuild can keep the trimmed build in step with
# hunspell-sk. It does not re-plan: entries that hunspell-sk adds later stay out until
# someone runs `make trim` with the lists again, and removed ones simply drop.
retrim: $(DATA)/superlatives.tsv
	@test -f $(TRIM)/keep_stems.txt || { echo "no $(TRIM)/keep_stems.txt — run make trim first"; exit 1; }
	$(PYTHON) scripts/dic2dict.py $(UPSTREAM)/sk_SK.dic -o $(TRIM)/dictionary.dict --source-rev "$(REV)" \
	  --keep-stems $(TRIM)/keep_stems.txt --extra-entries $(DATA)/superlatives.tsv $(MORPH_ARGS)

# `clean` removes everything generated, but not the trim plan: keep_stems.txt and report.txt
# are committed and cannot be rebuilt without the frequency lists. `clean-plan` removes them too.
.PHONY: clean-plan
clean:
	rm -f $(DATA)/dictionary.dict $(DATA)/annotations.json $(DATA)/superlatives.tsv
	rm -f $(TRIM)/dictionary.dict $(TRIM)/stem_freq.tsv $(TRIM)/costs.tsv

clean-plan: clean
	rm -rf $(TRIM)
