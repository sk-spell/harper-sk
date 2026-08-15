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
"""freq_join.py — join hunspell sk_SK.dic stems with corpus lemma frequencies.

The frequency lists are used *only as a selection criterion* (which hunspell stems to keep):
no word from a corpus ever enters the published dictionary. See PLAN.md, licence analysis.

Usage:
    freq_join.py --dic upstream-hunspell-sk/sk_SK.dic \
                 --snk data/snk_lemma.txt.bz2 \
                 [--os data/opensubtitles_sk_freq.txt.gz] \
                 -o measurements/stem_freq.tsv

Output (TSV, one row per .dic entry):
    stem  flags  pos  freq_snk  snk_match  freq_os  os_match

*_match:  exact | lower | none   (`lower` = matched case-insensitively)
The two frequency columns come from different corpora and are NOT comparable as raw
numbers — normalisation is done downstream in plan_cut.py.
"""
import argparse
import bz2
import gzip
import re
import sys
from collections import defaultdict

POS_RE = re.compile(r"\bpo:([a-z_]+)")


def open_maybe_compressed(path):
    if path.endswith(".bz2"):
        return bz2.open(path, "rt", encoding="utf-8", errors="replace")
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, encoding="utf-8", errors="replace")


def read_dic(path):
    """Yield (stem, flags, pos) for every entry of a hunspell .dic file."""
    with open(path, encoding="utf-8") as f:
        first = f.readline()
        if not first.strip().isdigit():
            print(f"warning: first line of {path} is not a count", file=sys.stderr)
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            head = re.split(r"[\t ]", line, maxsplit=1)
            word_part = head[0]
            morph = head[1] if len(head) > 1 else ""
            if "/" in word_part:
                stem, flags = word_part.split("/", 1)
            else:
                stem, flags = word_part, ""
            m = POS_RE.search(morph)
            if stem.strip():
                yield stem.strip(), flags.strip(), (m.group(1) if m else "")


def read_freq(path):
    """Return ({lemma: freq}, {lemma.lower(): freq}); duplicates are summed."""
    freq = defaultdict(int)
    with open_maybe_compressed(path) as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                parts = line.rsplit(" ", 1)
            if len(parts) < 2:
                continue
            lemma, n = parts[0], parts[-1]
            try:
                freq[lemma] += int(n)
            except ValueError:
                continue
    lower = defaultdict(int)
    for lemma, n in freq.items():
        lower[lemma.lower()] += n
    return freq, lower


def lookup(stem, freq, lower):
    if not freq:
        return 0, "none"
    if stem in freq:
        return freq[stem], "exact"
    if stem.lower() in lower:
        return lower[stem.lower()], "lower"
    return 0, "none"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dic", required=True)
    ap.add_argument("--snk", required=True, help="SNK prim lemma frequency list")
    ap.add_argument("--os", help="OpenSubtitles frequency list (secondary)")
    ap.add_argument("--extra", help="extra flag-less entries as <form>TAB<pos> "
                                    "(e.g. superlatives from gen_superlatives.py); they are "
                                    "appended after the .dic rows and cost one form each")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    snk, snk_lower = read_freq(a.snk)
    print(f"SNK: {len(snk):,} lemmas", file=sys.stderr)
    os_freq, os_lower = (read_freq(a.os) if a.os else ({}, {}))
    if a.os:
        print(f"OpenSubtitles: {len(os_freq):,} entries", file=sys.stderr)

    def entries():
        yield from read_dic(a.dic)
        if a.extra:
            n = 0
            with open(a.extra, encoding="utf-8") as f:
                for raw in f:
                    form, _, pos = raw.rstrip("\n").partition("\t")
                    if form:
                        n += 1
                        yield form, "", pos
            print(f"extra flag-less entries: {n:,}", file=sys.stderr)

    stats = defaultdict(int)
    rows = []
    for stem, flags, pos in entries():
        f_snk, m_snk = lookup(stem, snk, snk_lower)
        f_os, m_os = lookup(stem, os_freq, os_lower)
        stats[f"snk:{m_snk}"] += 1
        stats[f"os:{m_os}"] += 1
        if m_snk == "none" and m_os == "none":
            stats["no_freq_at_all"] += 1
        rows.append((stem, flags, pos, f_snk, m_snk, f_os, m_os))

    with open(a.out, "w", encoding="utf-8") as f:
        f.write("stem\tflags\tpos\tfreq_snk\tsnk_match\tfreq_os\tos_match\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")

    total = len(rows)
    print(f"stems: {total:,}", file=sys.stderr)
    for k in sorted(stats):
        print(f"  {k:20s} {stats[k]:7,}  ({stats[k] / total:5.1%})", file=sys.stderr)
    print(f"→ {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
