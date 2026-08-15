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
#
# NOTE: this script only *generates* data. The generated dictionary data is
# derived from sk-spell/hunspell-sk and stays under MPL-2.0 — see NOTICE.
"""gen_superlatives.py — materialise Slovak superlatives that Harper cannot express.

Why this exists
---------------
`sk_SK.aff` licenses the `naj-` prefix through hunspell **continuation flags**: 226 suffix
rules emit comparative forms carrying `/Fs`, which lets prefix class `F` (`naj-`, `najne-`)
apply to *those forms only*. Harper's `annotations.json` has no equivalent — an `Expansion`
carries replacements and metadata, but cannot hand a flag to the form it produces
(`harper-core/src/spell/rune/expansion.rs`). Giving the stem the `F` flag directly is not a
substitute: Harper would cross-multiply `naj-` with the entire declension and accept
`najpekný`, `najpekného`… which are not words.

So the superlatives are materialised here: every form produced by a rule whose continuation
flag contains `F` gets `naj` and `najne` variants, emitted as flag-less entries. They cost one
word form each, so the frequency cut (`plan_cut.py`) can price them individually and keep the
common ones (`najlepší`, `najväčšia`) while dropping the long tail.

Verified against the source: `hunspell -d sk_SK -l` accepts `najčastejšie`, `najkrajší`,
`najnekrajší` and `najnečastejšie`, i.e. both prefixes are genuinely licensed.

Usage:
    gen_superlatives.py sk_SK.aff sk_SK.dic -o superlatives.tsv
Output: `<form>\t<pos>` per line, sorted, deduplicated.
"""
import argparse
import re
import sys
from collections import Counter

# Prefixes of class F, in the order they appear in sk_SK.aff.
PREFIXES = ("naj", "najne")

POS_RE = re.compile(r"\bpo:([a-z_]+)")


def parse_comparative_rules(aff_path):
    """Suffix rules whose continuation flag contains F → (flag, remove, add, condition, pos)."""
    rules = []
    with open(aff_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.split("#")[0]
            parts = line.split()
            if len(parts) < 5 or parts[0] != "SFX":
                continue
            flag, remove, add, cond = parts[1], parts[2], parts[3], parts[4]
            if remove in ("Y", "N"):        # that is the class header line, not a rule
                continue
            cont = ""
            if "/" in add:
                add, cont = add.split("/", 1)
            if "F" not in cont:
                continue
            m = POS_RE.search(" ".join(parts[4:]))
            rules.append((
                flag,
                "" if remove == "0" else remove,
                "" if add == "0" else add,
                cond,
                m.group(1) if m else "",
            ))
    return rules


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("aff")
    ap.add_argument("dic")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    rules = parse_comparative_rules(a.aff)
    by_flag = {}
    for flag, remove, add, cond, pos in rules:
        by_flag.setdefault(flag, []).append((remove, add, cond, pos))
    print(f"pravidlá s continuation flagom F: {len(rules)} v triedach {sorted(by_flag)}",
          file=sys.stderr)

    cond_cache = {}
    comparatives = {}
    stats = Counter()

    with open(a.dic, encoding="utf-8") as f:
        first = f.readline()
        if not first.strip().isdigit():
            print(f"warning: first line of {a.dic} is not a count", file=sys.stderr)
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            head, _, morph = line.partition("\t") if "\t" in line else line.partition(" ")
            head = head.strip()
            if "/" not in head:
                continue
            stem, flags = head.split("/", 1)
            # Only 60 of the 225 rules carry a `po:` tag, so fall back to the stem's own
            # part of speech — a comparative of an adjective is still an adjective.
            m = POS_RE.search(morph)
            stem_pos = m.group(1) if m else ""
            touched = False
            for flag, frules in by_flag.items():
                if flag not in flags:
                    continue
                for remove, add, cond, pos in frules:
                    rx = cond_cache.setdefault(cond, re.compile(cond + "$"))
                    if not rx.search(stem):
                        continue
                    if remove and not stem.endswith(remove):
                        continue
                    form = (stem[: len(stem) - len(remove)] if remove else stem) + add
                    tag = pos or stem_pos
                    # a form can come from several rules; adjective wins over adverb
                    if form not in comparatives or (
                        tag == "adjective" and comparatives[form] != "adjective"
                    ):
                        comparatives[form] = tag
                    touched = True
            if touched:
                stats["stems"] += 1

    print(f"kmeňov s komparatívom: {stats['stems']:,} · komparatívnych tvarov: "
          f"{len(comparatives):,}", file=sys.stderr)

    with open(a.out, "w", encoding="utf-8") as out:
        n = 0
        for form in sorted(comparatives):
            pos = comparatives[form]
            for prefix in PREFIXES:
                out.write(f"{prefix}{form}\t{pos}\n")
                n += 1
    print(f"zapísaných superlatívov: {n:,} → {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
