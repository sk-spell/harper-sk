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
| `data/dictionary.dict` | word list — 159 692 stems with affix and part-of-speech flags |
| `data/annotations.json` | affix classes — 30 classes, 3 458 rules |
| `scripts/dic2dict.py` | `sk_SK.dic` → `dictionary.dict` |
| `scripts/aff2annotations.py` | `sk_SK.aff` → `annotations.json` |
| `Makefile` | fetch the source, rebuild both files |

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

## How faithful is the translation

The generated data was expanded and compared, form by form, against the
reference expansion produced by hunspell's own `unmunch`:

| | count | |
|---|---:|---|
| identical | 2 222 960 | 99.53 % |
| only in Harper | 10 598 | bare stems, which `unmunch` does not emit |
| only in hunspell | 5 641 | lost to Harper's case folding, see below |

The 5 641 missing forms are not a translation error. Harper folds case when
building its dictionary, so when the source contains both a lower-case and a
capitalised spelling of the same word — `abakus` and `Abakus` — only the
capitalised one survives, taking all inflected forms of the other with it.
That is a Harper limitation, tracked upstream, not a defect of the source
dictionary.

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
