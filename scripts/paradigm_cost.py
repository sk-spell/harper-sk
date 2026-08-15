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
"""paradigm_cost.py — how many word forms each dictionary entry expands into.

This is the cost side of the trim: memory scales with expanded forms, not with entries,
and Slovak entries differ wildly — an adjective averages 42 forms, a noun 9, a flag-less
entry exactly 1. Emitted in input order so `plan_cut.py` can zip it with the frequency table.

Usage: paradigm_cost.py data/dictionary.dict data/annotations.json -o costs.tsv
Output: <word>\t<flags>\t<forms>
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from expand import expand_word, load_affixes, parse_word_list  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dictionary")
    ap.add_argument("annotations")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    affixes, _ = load_affixes(a.annotations)
    total = entries = 0
    with open(a.out, "w", encoding="utf-8") as out:
        for word, flags in parse_word_list(a.dictionary):
            n = len(expand_word(word, flags, affixes))
            out.write(f"{word}\t{flags}\t{n}\n")
            entries += 1
            total += n

    print(f"entries: {entries:,} · summed forms: {total:,} "
          f"(average {total / max(1, entries):.1f})", file=sys.stderr)
    print(f"→ {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
