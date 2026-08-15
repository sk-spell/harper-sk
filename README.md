# harper-sk

Slovak dictionary data for [Harper](https://github.com/Automattic/harper), the
offline grammar and spell checker, generated from
[sk-spell/hunspell-sk](https://github.com/sk-spell/hunspell-sk).

**The dictionary itself is the work of the sk-spell project — Zdenko Podobný and
contributors.** This repository does not add lexical data. It only translates
the hunspell files into the two files Harper reads, and keeps that translation
re-runnable so every new hunspell-sk release can be picked up by re-running one
command.

## What is in here

| Path | What it is |
|---|---|
| `data/dictionary.dict` | word list — 800 386 entries, expanding to 2.9 M word forms |
| `data/annotations.json` | affix classes — 30 classes, 3 458 rules |
| `data/trimmed/dictionary.dict` | the same, trimmed to a budget of word forms (see below) |
| `scripts/dic2dict.py` | `sk_SK.dic` → `dictionary.dict` |
| `scripts/aff2annotations.py` | `sk_SK.aff` → `annotations.json` |
| `scripts/gen_superlatives.py` | the `naj-` forms Harper's format cannot express |
| `scripts/expand.py` | expand the data into word forms, without building Harper |
| `scripts/check_data.py` | precision and coverage checks against hunspell |
| `scripts/paradigm_cost.py`, `freq_join.py`, `plan_cut.py` | the trim |
| `Makefile` | fetch the source, rebuild, trim |

Both data files are generated. Do not edit them by hand — fix the generator, or
report the issue against hunspell-sk if the source data is wrong.

## Rebuilding

```sh
make            # clone or update hunspell-sk, then regenerate both files
make build      # regenerate only
make build UPSTREAM=../hunspell-sk   # build against an existing checkout
```

Requires Python 3 and git; no third-party packages. The generated files record
the exact hunspell-sk revision they came from in their header, so it is always
possible to tell which upstream release a given build corresponds to.

## Staying in sync with hunspell-sk

A scheduled workflow (`.github/workflows/sync-upstream.yml`) rebuilds the data
every Monday against the current hunspell-sk and opens a pull request if the
result differs. Picking up a new release of the dictionary is therefore a review
of a generated diff, not a task anyone has to remember — and it costs the
hunspell-sk side nothing. The workflow can also be triggered by hand from the
Actions tab.

## Using the data in Harper

Harper embeds its dictionary at compile time
(`harper-core/src/spell/mutable_dictionary.rs`), so the Slovak build is made by
replacing the two English files and rebuilding:

```sh
cp data/dictionary.dict data/annotations.json path/to/harper/harper-core/
cargo build --release
```

## Trimming it down

Harper keeps its dictionary in memory, and memory scales with *expanded word
forms*. Slovak inflects heavily — 2.9 M forms out of 800 k entries, roughly 1.5 GB
resident — which is more than an editor plugin can ask for. `make trim` therefore
produces a smaller build under a budget of forms:

```sh
make trim FREQ_SNK=../snk_lemma.txt.bz2 FREQ_OS=../sk_full.txt BUDGET=620000
```

The budget is spent where it buys the most text: value is the frequency of the
whole paradigm, cost is the number of forms it expands into, and closed classes
(pronouns, prepositions, conjunctions, particles, numerals) are always kept
because they are cheap and their absence is the most conspicuous kind of false
positive. At a 620 000-form budget the result keeps 58 836 entries and 607 k
forms — about 360 MB in Harper, in the same range as the German dictionary —
while still covering 90.4 % of the running text of a reference corpus, against
91.5 % for the untrimmed build.

`data/trimmed/keep_stems.txt` records exactly which entries survived, so a trim
can be reproduced without access to the frequency lists.

**The frequency lists are a selection criterion only.** Not one word from them
enters the data: every word still comes from hunspell-sk, and the lists merely
decide which of those entries to keep. Entry selection was filtered using the
lemma frequency list of the prim-11.0-public-all corpus, Slovak National Corpus,
Ľ. Štúr Institute of Linguistics, Slovak Academy of Sciences,
<https://korpus.juls.savba.sk>, with the OpenSubtitles frequency list
([hermitdave/FrequencyWords](https://github.com/hermitdave/FrequencyWords), MIT)
as a secondary source for word forms the lemma list does not cover.

## How faithful is the translation

Two checks run in CI on every change (`.github/workflows/data-quality.yml`),
both using hunspell itself as the oracle, since it is the reference
implementation of the source dictionary:

| Check | Question | Current |
|---|---|---|
| precision | is every form we generate a word hunspell accepts? | 809 are not, 0.028 % |
| coverage | of the running text hunspell covers, how much do we lose? | 0.05 % |

Coverage is weighted by frequency on purpose: losing `už` and losing
`Alma-atanásobný` are not the same event.

`unmunch` is deliberately not used as the reference. It over-generates — hunspell
rejects some 800 k of the 3.6 M forms it emits — and under-generates at the same
time, because it ignores the continuation flags that license `naj-` superlatives.
Agreement with it measures a third implementation's quirks rather than
correctness.

One known gap is not ours: Harper folds case when building its dictionary, so
when the source holds both a lower-case word and a capitalised spelling of it —
`kde` and the acronym `KDE`, `urán` and the planet `Urán` — only one survives,
taking every inflected form of the other with it. That costs 5 522 forms here,
including words as common as `už` and `kde`, and is tracked upstream in
[Automattic/harper#2411](https://github.com/Automattic/harper/issues/2411).

## Licensing

This repository is deliberately mixed, file by file:

- **`data/` — MPL-2.0**, inherited from hunspell-sk. Not relicensed.
- **`scripts/`, `Makefile` — Apache-2.0**, so the tooling can be contributed to
  Harper itself if that turns out to be useful.

MPL-2.0 is a file-level copyleft licence and is compatible with Apache-2.0 in
this arrangement: the data files stay under MPL-2.0 wherever they travel,
including inside an Apache-2.0 project. See [`NOTICE`](NOTICE) for the full
statement.

## Maintenance

Slovak data for Harper is maintained by Branislav Klocok. Issues about the
*words themselves* — a missing word, a wrong inflection — belong to
[hunspell-sk](https://github.com/sk-spell/hunspell-sk), because that is where
the dictionary lives. Issues about the *translation* into Harper's format
belong here.
