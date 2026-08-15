#!/usr/bin/env python3
#
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2026 Branislav Klocok
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""expand.py — expand Harper dictionary data into the full list of word forms.

A stand-alone reimplementation of what `harper-core` does with `dictionary.dict` +
`annotations.json` (`src/spell/rune/`): apply every affix class a word carries, honouring
`kind`, `condition`, `remove`/`add` and `cross_product`.

It exists so the data can be checked **without** building Harper: the equivalence test
compares this output against hunspell's own `unmunch`, and the coverage test feeds it to
`hunspell -l`. Reimplementing it is the point — a test that expanded the data with Harper
itself could not tell a translation bug from a Harper bug.

Deliberately *not* reproduced here: Harper's case folding, which drops a word when another
entry differs only in capitalisation (`kde` vs the acronym `KDE`). That behaviour is upstream
issue #2411; hiding it here would hide the very thing worth measuring.

Usage: expand.py dictionary.dict annotations.json [-o forms.txt]
"""
import argparse
import json
import re
import sys


def parse_word_list(path):
    """Yield (word, flags) — same filtering as harper-core's `parse_word_list`."""
    with open(path, encoding="utf-8") as f:
        first = f.readline()
        if not first.strip().isdigit():
            print(f"warning: first line of {path} is not an entry count", file=sys.stderr)
        for raw in f:
            line = raw.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            entry = line.split("#", 1)[0].rstrip() if "#" in line else line.rstrip()
            if not entry:
                continue
            word, sep, attr = entry.partition("/")
            yield word, (attr if sep else "")


def compile_condition(cond, kind):
    """hunspell condition → anchored regex (suffix: at the end, prefix: at the start)."""
    if cond in (".", ""):
        return None
    return re.compile(cond + "$" if kind == "suffix" else "^" + cond)


def load_affixes(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    affixes = {}
    for flag, a in data.get("affixes", {}).items():
        kind = a["kind"]
        rules = []
        for r in a.get("replacements", []):
            rules.append((r.get("remove", ""), r.get("add", ""),
                          compile_condition(r.get("condition", "."), kind)))
        affixes[flag] = {"kind": kind, "cross": a.get("cross_product", False), "rules": rules}
    return affixes, set(data.get("properties", {}))


def apply_rule(word, kind, remove, add):
    if kind == "suffix":
        if remove:
            if not word.endswith(remove):
                return None
            return word[: len(word) - len(remove)] + add
        return word + add
    if remove:
        if not word.startswith(remove):
            return None
        return add + word[len(remove):]
    return add + word


def expand_word(word, flags, affixes):
    """All forms of one entry: the base, every affix, and prefix×suffix cross products."""
    forms = {word}
    prefixes, suffixes = [], []
    for flag in flags:
        a = affixes.get(flag)
        if not a:
            continue                     # property flag or unknown — carries no expansion
        (prefixes if a["kind"] == "prefix" else suffixes).append(a)

    suffixed = []
    for a in suffixes:
        for remove, add, cond in a["rules"]:
            if cond and not cond.search(word):
                continue
            form = apply_rule(word, "suffix", remove, add)
            if form:
                forms.add(form)
                if a["cross"]:
                    suffixed.append(form)

    for a in prefixes:
        bases = [word] + (suffixed if a["cross"] else [])
        for base in bases:
            for remove, add, cond in a["rules"]:
                if cond and not cond.search(base):
                    continue
                form = apply_rule(base, "prefix", remove, add)
                if form:
                    forms.add(form)
    return forms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dictionary")
    ap.add_argument("annotations")
    ap.add_argument("-o", "--out", default="-")
    a = ap.parse_args()

    affixes, properties = load_affixes(a.annotations)
    print(f"affix classes: {len(affixes)} · property flags: {len(properties)}", file=sys.stderr)

    all_forms = set()
    entries = 0
    for word, flags in parse_word_list(a.dictionary):
        entries += 1
        all_forms |= expand_word(word, flags, affixes)

    out = sys.stdout if a.out == "-" else open(a.out, "w", encoding="utf-8")
    for form in sorted(all_forms):
        out.write(form + "\n")
    if out is not sys.stdout:
        out.close()

    print(f"entries: {entries:,} → forms: {len(all_forms):,}", file=sys.stderr)


if __name__ == "__main__":
    main()
