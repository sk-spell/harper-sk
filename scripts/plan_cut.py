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
"""plan_cut.py — pick which hunspell stems to keep, under a budget of expanded word forms.

This is the knapsack step of variant B:
    value = frequency of the whole paradigm (SNK lemma frequency)
    cost  = number of word forms the stem expands into (measured by `paradigm_cost`)

Rules that override the pure ratio (see MASTER_PLAN / PLAN.md):
  * closed classes (pronouns, prepositions, conjunctions, particles, interjections,
    numerals) are ALWAYS kept — they are cheap and their absence is the most
    embarrassing kind of false positive,
  * proper names are cut aggressively (they are also a source of case-fold collisions),
  * stems with no corpus frequency at all keep a small floor value so that a
    reasonable part of the technical vocabulary survives (configurable).

Usage:
    plan_cut.py --freq measurements/stem_freq.tsv \
                --cost measurements/paradigm_cost.tsv \
                --budget 655674 \
                -o measurements/keep_stems.txt
"""
import argparse
import csv
import sys
from collections import Counter, defaultdict

CLOSED_CLASSES = {
    "pronoun",
    "preposition",
    "conjunction",
    "particle",
    "interjection",
    "number",
    "numeral",
}


def read_freq(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def read_cost(path):
    """paradigm_cost.tsv: stem \t flags \t forms (same order as the source .dic)."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            rows.append((parts[0], parts[1], int(parts[2])))
    return rows


def normalise_os(rows):
    """Scale OpenSubtitles counts onto the SNK scale using the overlap (median ratio)."""
    ratios = []
    for r in rows:
        fs, fo = int(r["freq_snk"]), int(r["freq_os"])
        if fs > 0 and fo > 0:
            ratios.append(fs / fo)
    if not ratios:
        return 1.0
    ratios.sort()
    return ratios[len(ratios) // 2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freq", required=True)
    ap.add_argument("--cost", required=True)
    ap.add_argument("--budget", type=int, required=True, help="max expanded word forms")
    ap.add_argument("-o", "--out", required=True, help="keep list for dic2dict --keep-stems")
    ap.add_argument("--proper-penalty", type=float, default=0.25,
                    help="value multiplier for capitalised stems and acronyms (default 0.25)")
    ap.add_argument("--unknown-floor", type=float, default=0.0,
                    help="value given to stems with no corpus frequency (default 0)")
    ap.add_argument("--keep-bare", action="store_true",
                    help="keep every entry that carries no affix flags (they cost one form each "
                         "and are usually supplementary inflected forms of kept lemmas)")
    ap.add_argument("--report", help="write a per-POS report here")
    a = ap.parse_args()

    freq_rows = read_freq(a.freq)
    cost_rows = read_cost(a.cost)
    if len(cost_rows) < len(freq_rows):
        # Rows appended by `freq_join.py --extra` are flag-less: exactly one form each,
        # so there is nothing for `paradigm_cost` to measure.
        extra = len(freq_rows) - len(cost_rows)
        print(f"cost file is {extra:,} rows short — treating those as one form each "
              f"(flag-less entries)", file=sys.stderr)
        cost_rows += [(r["stem"], "", 1) for r in freq_rows[len(cost_rows):]]
    elif len(cost_rows) > len(freq_rows):
        sys.exit(f"row count mismatch: freq {len(freq_rows)} vs cost {len(cost_rows)}")

    scale = normalise_os(freq_rows)
    print(f"OpenSubtitles → SNK scale factor (median of overlap): {scale:.2f}", file=sys.stderr)

    # A stem can occur several times in the .dic (homographs with different flags).
    # `dic2dict --keep-stems` matches by the stem string, so all of its entries share one
    # decision — group them and let the cost be the sum of all their forms.
    grouped = {}
    for r, (cstem, _cflags, forms) in zip(freq_rows, cost_rows):
        if r["stem"] != cstem:
            sys.exit(f"row misalignment: {r['stem']!r} vs {cstem!r}")
        stem = r["stem"]
        f_snk, f_os = int(r["freq_snk"]), int(r["freq_os"])
        # ⚠️ Take the MAXIMUM of the two, do not prefer SNK.
        # sk_SK.dic stores a lot of inflected forms as separate bare entries (`peci`, `pece`
        # next to `pec/D`). SNK is a *lemma* list, so it counts almost all of their occurrences
        # under the base lemma and gives the bare entry a near-zero count — which used to cut
        # exactly those forms whose lemma the dictionary keeps. OpenSubtitles is a *form* list,
        # so it values them correctly; scaling brings it onto the SNK scale.
        value = max(float(f_snk), f_os * scale)
        if value == 0:
            value = a.unknown_floor
        pos = r["pos"]
        is_proper = pos == "acronym" or (stem[:1].isupper() and stem[:1].isalpha())
        if is_proper:
            value *= a.proper_penalty
        g = grouped.setdefault(stem, {
            "stem": stem, "pos": pos, "forms": 0, "value": value,
            "closed": False, "proper": is_proper, "snk": 0.0, "bare": True,
        })
        if r["flags"]:
            g["bare"] = False
        g["forms"] += max(1, forms)
        g["value"] = max(g["value"], value)
        g["snk"] = max(g["snk"], float(f_snk))
        g["closed"] = g["closed"] or pos in CLOSED_CLASSES
        g["proper"] = g["proper"] and is_proper
        if not g["pos"]:
            g["pos"] = pos

    items = list(grouped.values())
    total_forms = sum(i["forms"] for i in items)
    total_value = sum(i["snk"] for i in items)

    # 1. closed classes first, unconditionally
    keep = {}
    used = 0
    for i in items:
        if i["closed"]:
            keep[i["stem"]] = i
            used += i["forms"]
    print(f"closed classes: {len(keep):,} stems, {used:,} forms", file=sys.stderr)

    # 1b. optionally every affix-less entry (one form each)
    if a.keep_bare:
        before = len(keep)
        for i in items:
            if i["bare"] and i["stem"] not in keep:
                keep[i["stem"]] = i
                used += i["forms"]
        print(f"bare entries:   {len(keep) - before:,} stems, {used:,} forms cumulative",
              file=sys.stderr)

    # 2. everything else greedily by value per form
    rest = sorted(
        (i for i in items if i["stem"] not in keep),
        key=lambda i: i["value"] / i["forms"],
        reverse=True,
    )
    for i in rest:
        if used + i["forms"] > a.budget:
            continue
        keep[i["stem"]] = i
        used += i["forms"]

    kept_snk = sum(i["snk"] for i in keep.values())

    with open(a.out, "w", encoding="utf-8") as f:
        for stem in keep:
            f.write(stem + "\n")

    print(f"\nbudget:        {a.budget:,} forms", file=sys.stderr)
    print(f"kept stems:    {len(keep):,} / {len({i['stem'] for i in items}):,}", file=sys.stderr)
    print(f"kept forms:    {used:,} / {total_forms:,}  ({used / total_forms:.1%})", file=sys.stderr)
    print(f"kept SNK mass: {kept_snk / total_value:.3%} of the corpus tokens covered by the "
          f"full dictionary", file=sys.stderr)
    print(f"→ {a.out}", file=sys.stderr)

    by_pos = defaultdict(lambda: Counter())
    for i in items:
        k = i["pos"] or "(none)"
        by_pos[k]["stems"] += 1
        by_pos[k]["forms"] += i["forms"]
        if i["stem"] in keep:
            by_pos[k]["kept_stems"] += 1
            by_pos[k]["kept_forms"] += i["forms"]
    lines = [f"{'pos':12s} {'stems':>8s} {'kept':>8s} {'%':>6s} {'forms':>10s} {'kept':>10s} {'%':>6s}"]
    for k in sorted(by_pos, key=lambda k: -by_pos[k]["forms"]):
        c = by_pos[k]
        lines.append(
            f"{k:12s} {c['stems']:8,} {c['kept_stems']:8,} {c['kept_stems'] / c['stems']:6.1%} "
            f"{c['forms']:10,} {c['kept_forms']:10,} {c['kept_forms'] / c['forms']:6.1%}"
        )
    report = "\n".join(lines)
    print("\n" + report, file=sys.stderr)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            f.write(report + "\n")


if __name__ == "__main__":
    main()
