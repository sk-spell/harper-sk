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
| `data/dictionary.dict` | word list — 800 386 entries, expanding to 2 877 771 word forms |
| `data/annotations.json` | affix classes — 30 classes, 3 458 rules; suggestion hints (REP, MAP, KEY, TRY) |
| `data/trimmed/dictionary.dict` | the same, trimmed to a budget of word forms (see below) |
| `scripts/dic2dict.py` | `sk_SK.dic` → `dictionary.dict` |
| `scripts/aff2annotations.py` | `sk_SK.aff` → `annotations.json` |
| `scripts/gen_superlatives.py` | the `naj-` forms Harper's format cannot express |
| `scripts/expand.py` | expand the data into word forms, without building Harper |
| `scripts/check_data.py` | precision and coverage checks against hunspell, memory budget of the trim |
| `scripts/freq_join.py`, `plan_partial.py`, `apply_plan.py` | the trim |
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

### Morphology (opt-in)

hunspell-sk tags its affix rules with case, number, gender and person. Harper can
carry these as word metadata, but only per affix class, so passing them on means
splitting each class into one sub-class per tag signature:

```sh
make build MORPHOLOGY=verbs   # person, number, mood and past-tense gender of verbs
make build MORPHOLOGY=full    # plus case, number, gender and animacy of nouns and adjectives
```

The word forms stay exactly the same; only the flags on each entry change. `verbs`
works with Harper today. `full` needs the Locative, Instrumental and Vocative cases,
an animacy axis and an adjective slot in Harper's morphology, proposed in
[Dronakurl/harper#11](https://github.com/Dronakurl/harper/issues/11). The default is
`none`.

## Suggestion hints

`annotations.json` also carries a `suggestions` section with the directives hunspell uses
to rank its suggestions: the 53 `REP` pairs, the 17 `MAP` groups of related letters
(`a á ä`, `t ť`, …), the `KEY` keyboard rows and the `TRY` letter order from `sk_SK.aff`.
A reader that does not know the section ignores it. The importer works for any hunspell
dictionary and honours its `SET` encoding:

```sh
python3 scripts/aff2annotations.py path/to/xx_XX.aff --suggestions-only -o hints.json
```

Pass `--no-suggestions` to leave the section out.

## Staying in sync with hunspell-sk

A scheduled workflow (`.github/workflows/sync-upstream.yml`) rebuilds the data
every Monday against the current hunspell-sk and opens a pull request if the
result differs. Picking up a new release of the dictionary is therefore a review
of a generated diff, not a task anyone has to remember — and it costs the
hunspell-sk side nothing. The workflow can also be triggered by hand from the
Actions tab.

## Trying Slovak in the browser and in Thunderbird

The releases of this repository carry unofficial builds of Harper's browser extensions with Slovak support. They are for trying the Slovak data out until Slovak is part of an official Harper release.

Thunderbird: open Add-ons and Themes, choose Install Add-on From File from the gear menu and pick the .xpi. Open a new message and write some Slovak.

Firefox: open the signed .xpi from the release page in Firefox and confirm the installation. Harper only checks the sites it is enabled on, so allow the extension on the pages you want it for in the add-on permissions.

Chrome: unzip the .zip, open chrome://extensions, turn on developer mode, choose Load unpacked and select the folder. Chrome shows a developer-mode warning on every start.

The extensions start in the language of the browser's or Thunderbird's interface. If that is not Slovak, Harper starts in English, underlines most Slovak words and shows US in the badge next to the text field. To switch, click the Harper button in the toolbar, choose Settings and, under Languages, pick Slovenčina from "Add a language…". Adding it does not switch yet: put the cursor in a text field and press Ctrl+Shift+Space, which moves between the chosen languages. The first switch can take several seconds while the Slovak dictionary loads, and the badge then shows SK.

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
make trim FREQ_SNK=../snk_lemma.txt.bz2 FREQ_OS=../sk_full.txt BUDGET=900000
```

The trim keeps paradigm cells, not whole entries. With `--morphology full` every
inflection class is split into sub-classes, one per case, number and gender, each
with its own flag, so an entry can keep the cells running text uses and drop the
rest: plain data, nothing Harper has to support. A whole adjective costs about 50
forms and text uses a handful of them, so the same memory holds far more words.
Each cell is valued by how often its forms occur, and where the subtitles never saw
a form, by the lemma's frequency times the share such a cell usually carries. The
flags that hold the base form's own morphology always stay with it, and so does every
class whose forms are in the build anyway, so a kept form keeps all its readings
(`pekného` stays both accusative and genitive). Closed classes (pronouns,
prepositions, conjunctions, particles, numerals) are kept whole.
Valuing forms rather than lemmas also keeps frequent words that hunspell-sk only has
as a form of a rare entry: `tomu` is the genitive of `tomus` there, `späť` an
imperative of `spätiť`, and a cut by lemma frequency dropped both.

Measured on text that played no part in the selection (office documents and
Slovak news), cells instead of entries halved the words the trim wrongly flags at
the same memory. The cost is a new kind of miss: an entry is in, one of its rarer
forms is not, and the first suggestion is then often another form of the same
word. A larger budget reduces both, which is why it is set close to Harper's limit.

`BUDGET` counts distinct word forms, which is what Harper's memory scales with.
Harper keeps its words in a hash table that doubles above 917 504 words; resident
memory for Slovak then jumps from about 415 MB to about 785 MB. 900 000 forms are
about 898 000 words in Harper. `check_data.py budget` counts the words the way
Harper does (case folded) and fails above 910 000, in `make trim`, `make retrim`
and in CI, so a re-plan or a growing source cannot cross the line unnoticed.
`data/trimmed/report.txt` shows how many entries are kept whole and how many in part.

`data/trimmed/keep_entries.tsv` records the plan entry by entry: which entries stay,
and of a partial one, which affix classes. Classes are named by a short hash of
their description in `annotations.json`, so the plan survives a renumbering of the
sub-class flags. A trim can therefore be reproduced without the frequency lists:
`make retrim` applies the plan to the current data, and the weekly rebuild does
exactly that. It does not re-plan, so entries hunspell-sk adds later stay out of
the trimmed build until someone runs `make trim` with the lists again.

**The frequency lists are a selection criterion only.** Not one word from them
enters the data: every word still comes from hunspell-sk, and the lists merely
decide which of those entries to keep. Entry selection was filtered using the
lemma frequency list of the prim-11.0-public-all corpus, Slovak National Corpus,
Ľ. Štúr Institute of Linguistics, Slovak Academy of Sciences, v. v. i.,
<https://korpus.sk>, with the OpenSubtitles frequency list
([hermitdave/FrequencyWords](https://github.com/hermitdave/FrequencyWords), MIT)
valuing individual word forms.

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
taking every inflected form of the other with it. Of the 2 877 771 forms this
data expands to, Harper therefore builds 2 870 065: the 7 706 it drops all have
a case twin in the build, and they include words as common as `už` and `kde`.
It is tracked upstream in
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
