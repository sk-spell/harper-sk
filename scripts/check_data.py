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
"""check_data.py — guard the generated data against translation regressions.

Two checks, both using **hunspell itself** as the oracle, because it is the reference
implementation of the source dictionary:

  precision  Every form we generate must be a word hunspell accepts. Catches a translated
             affix rule that fires too widely and starts inventing words.
  coverage   Of the word forms hunspell accepts in a frequency list, how much running text do
             we fail to cover? Catches an affix class that silently stopped expanding.

Why not `unmunch` as the reference: it over-generates (hunspell rejects ~800k of its ~3.6M
forms) and under-generates at the same time (it ignores continuation flags, so it emits no
`naj-` superlatives at all). A test against it measures agreement with a third implementation's
quirks, not correctness. Frequency weighting matters for the same reason: losing `už` and
losing `Alma-atanásobný` are not the same event.

    check_data.py precision --dict data/dictionary.dict --annotations data/annotations.json \
                            --hunspell upstream/hunspell-sk/sk_SK
    check_data.py coverage  --dict ... --annotations ... --hunspell ... --freq sk_full.txt

Exit code 1 when a threshold is exceeded.
"""
import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from expand import expand_word, load_affixes, parse_word_list  # noqa: E402

WORD_RE = re.compile(r"^[^\W\d_]+(?:[-'’][^\W\d_]+)*$", re.UNICODE)


def expand_all(dict_path, ann_path):
    affixes, _ = load_affixes(ann_path)
    forms = set()
    for word, flags in parse_word_list(dict_path):
        forms |= expand_word(word, flags, affixes)
    return forms


def hunspell_rejects(words, base):
    """Tokens hunspell does not accept, as a set.

    ⚠️ Not a line-for-line answer: hunspell splits at hyphens, so one input word can produce
    several output tokens (`mm-hmm` → `mm`, `hmm`). Callers therefore have to test membership
    of the whole form (`form in rejects`), not count output lines — counting them overstates
    the number of rejected words roughly threefold on this data.
    """
    payload = "\n".join(words)
    res = subprocess.run(["hunspell", "-d", base, "-l"], input=payload,
                         capture_output=True, text=True)
    if res.returncode not in (0, 1):
        sys.exit(f"hunspell failed: {res.stderr[:300]}")
    return {w for w in res.stdout.split("\n") if w}


def read_freq(path, top):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2 or not WORD_RE.match(parts[0]):
                continue
            try:
                rows.append((parts[0], int(parts[-1])))
            except ValueError:
                continue
    rows.sort(key=lambda kv: -kv[1])
    return rows[:top]


def cmd_precision(a):
    forms = expand_all(a.dict, a.annotations)
    rejects = hunspell_rejects(forms, a.hunspell)
    invented = {f for f in forms if f in rejects}
    share = len(invented) / max(1, len(forms))
    print(f"generated forms: {len(forms):,}")
    print(f"hunspell rejects: {len(invented):,} ({share:.3%})")
    for w in sorted(invented)[:20]:
        print(f"   {w}")
    if share > a.max_invented:
        print(f"\nFAIL: {share:.3%} of generated forms are not words hunspell knows "
              f"(limit {a.max_invented:.3%})")
        return 1
    print(f"\nOK: within the {a.max_invented:.3%} limit")
    return 0


def cmd_coverage(a):
    rows = read_freq(a.freq, a.top)
    if not rows:
        sys.exit(f"no usable rows in {a.freq}")
    rejected = hunspell_rejects([w for w, _ in rows], a.hunspell)
    forms = expand_all(a.dict, a.annotations)

    known_mass = lost_mass = 0
    lost = []
    for w, n in rows:
        if w in rejected:
            continue
        known_mass += n
        if w not in forms and w.lower() not in forms and w.lower().capitalize() not in forms:
            lost.append((w, n))
            lost_mass += n

    share = lost_mass / max(1, known_mass)
    print(f"frequency list: {len(rows):,} forms, {known_mass:,} occurrences hunspell knows")
    print(f"we are missing: {len(lost):,} forms, {lost_mass:,} occurrences ({share:.2%})")
    for w, n in sorted(lost, key=lambda kv: -kv[1])[:20]:
        print(f"   {n:9,}x  {w}")
    if share > a.max_loss:
        print(f"\nFAIL: {share:.2%} of known running text is not covered "
              f"(limit {a.max_loss:.2%})")
        return 1
    print(f"\nOK: within the {a.max_loss:.2%} limit")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("precision", "coverage"):
        p = sub.add_parser(name)
        p.add_argument("--dict", required=True)
        p.add_argument("--annotations", required=True)
        p.add_argument("--hunspell", required=True,
                       help="path to the hunspell dictionary without .aff/.dic")
        if name == "precision":
            p.add_argument("--max-invented", type=float, default=0.001,
                           help="fail above this share of generated forms hunspell rejects")
        else:
            p.add_argument("--freq", required=True)
            p.add_argument("--top", type=int, default=150000)
            p.add_argument("--max-loss", type=float, default=0.002,
                           help="fail above this share of known running text left uncovered")

    a = ap.parse_args()
    return cmd_precision(a) if a.cmd == "precision" else cmd_coverage(a)


if __name__ == "__main__":
    sys.exit(main())
