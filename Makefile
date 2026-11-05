# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Branislav Klocok
#
# Rebuild the Slovak Harper dictionary data from sk-spell/hunspell-sk.
#
#   make fetch    clone or update the hunspell-sk source
#   make build    regenerate data/dictionary.dict and data/annotations.json
#   make retrim   regenerate data/trimmed/dictionary.dict from the committed trim plan
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
MORPHOLOGY      ?= full
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
# Memory scales with distinct word forms, and a full Slovak dictionary expands to ~2.9 M of
# them — too much for an editor plugin. `make trim` keeps the most useful *paradigm cells*
# under a budget of forms: an entry may keep only some of its cases and numbers, which
# `--morphology full` makes expressible as plain data (see scripts/plan_partial.py).
#
# BUDGET is in distinct word forms. Harper keeps its words in a hash table that doubles above
# 917 504 words, so the budget sits below that with headroom; `check_data.py budget` fails
# the build before it gets there. 900 000 forms are ~898 000 words in Harper, ~415 MB.
#
# The frequency lists are a SELECTION CRITERION ONLY. Not one word from them enters the
# data — every word still comes from hunspell-sk. They are not redistributed here, so
# point the variables at your own copies:
#
#   FREQ_SNK  lemma frequency list of prim-11.0-public-all, Slovak National Corpus
#             https://korpus.juls.savba.sk/files/prim-11.0/
#   FREQ_OS   OpenSubtitles frequency list (MIT), hermitdave/FrequencyWords, sk_full.txt
#
#   make trim FREQ_SNK=../snk_lemma.txt.bz2 FREQ_OS=../sk_full.txt BUDGET=900000

BUDGET   ?= 900000
TRIM     ?= data/trimmed
FREQ_SNK ?=
FREQ_OS  ?=

.PHONY: trim retrim

trim: $(TRIM)/dictionary.dict
	@echo "trimmed to a budget of $(BUDGET) word forms"
	$(PYTHON) scripts/check_data.py budget --dict $(TRIM)/dictionary.dict --annotations $(DATA)/annotations.json

$(TRIM)/stem_freq.tsv: $(UPSTREAM)/sk_SK.dic $(DATA)/superlatives.tsv scripts/freq_join.py
	@test -n "$(FREQ_SNK)" || { echo "set FREQ_SNK (see the Makefile header)"; exit 1; }
	@mkdir -p $(TRIM)
	$(PYTHON) scripts/freq_join.py --dic $(UPSTREAM)/sk_SK.dic --snk $(FREQ_SNK) \
	  $(if $(FREQ_OS),--os $(FREQ_OS),) --extra $(DATA)/superlatives.tsv -o $@

$(TRIM)/keep_entries.tsv: $(TRIM)/stem_freq.tsv $(DATA)/dictionary.dict $(DATA)/annotations.json scripts/plan_partial.py
	@test -n "$(FREQ_OS)" || { echo "set FREQ_OS — the cells are valued by form frequency"; exit 1; }
	$(PYTHON) scripts/plan_partial.py --dict $(DATA)/dictionary.dict --annotations $(DATA)/annotations.json \
	  --freq $(TRIM)/stem_freq.tsv --os $(FREQ_OS) --budget $(BUDGET) -o $@ --report $(TRIM)/report.txt

$(TRIM)/dictionary.dict: $(TRIM)/keep_entries.tsv $(DATA)/dictionary.dict $(DATA)/annotations.json scripts/apply_plan.py
	$(PYTHON) scripts/apply_plan.py $(DATA)/dictionary.dict $(DATA)/annotations.json $(TRIM)/keep_entries.tsv -o $@

# `make retrim` applies the committed plan (keep_entries.tsv) to the current full data and
# needs no frequency lists, so the weekly rebuild can keep the trimmed build in step with
# hunspell-sk. It does not re-plan: entries that hunspell-sk adds later stay out until
# someone runs `make trim` with the lists again, and removed or changed ones simply drop.
retrim: $(DATA)/dictionary.dict $(DATA)/annotations.json
	@test -f $(TRIM)/keep_entries.tsv || { echo "no $(TRIM)/keep_entries.tsv — run make trim first"; exit 1; }
	$(PYTHON) scripts/apply_plan.py $(DATA)/dictionary.dict $(DATA)/annotations.json $(TRIM)/keep_entries.tsv \
	  -o $(TRIM)/dictionary.dict
	$(PYTHON) scripts/check_data.py budget --dict $(TRIM)/dictionary.dict --annotations $(DATA)/annotations.json

# `clean` removes everything generated, but not the trim plan: keep_entries.tsv and report.txt
# are committed and cannot be rebuilt without the frequency lists. `clean-plan` removes them too.
.PHONY: clean-plan
clean:
	rm -f $(DATA)/dictionary.dict $(DATA)/annotations.json $(DATA)/superlatives.tsv
	rm -f $(TRIM)/dictionary.dict $(TRIM)/stem_freq.tsv

clean-plan: clean
	rm -rf $(TRIM)
