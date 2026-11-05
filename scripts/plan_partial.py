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
"""plan_partial.py — choose which affix classes of which entries the trimmed build keeps.

Memory scales with distinct word forms. A whole Slovak adjective costs ~50 of them, of which
running text uses a handful, so the trim does not keep or drop whole entries: it keeps
*paradigm cells*. With `--morphology full` every inflection class is split into sub-classes,
one per morphological signature (case × number × gender …), each with its own flag — so a
partial paradigm is plain data: an entry with some of its flags removed.

Units of selection, per entry:
  base      the entry word itself, together with every flag that carries the base's own
            morphology (`base_metadata`) and every sub-class that yields no new form here
            (accusative = nominative): metadata of a form that is in anyway,
  suffix f  the forms of one suffix sub-class,
  prefix p  the prefix (`ne-`, `naj-`) on the base,
  f × p     the prefix on the forms of f (cross product).
Each unit is charged its *realised* marginal cost — the distinct forms that actually appear and
are not in the build yet; a kept prefix applies to every kept cross-product suffix — so the
budget is exact in distinct forms. Afterwards every kept entry also gets each class whose forms
are all in the build already: it costs no form, and it gives a kept form the readings of its
dropped homonymous cells (accusative and genitive of an adjective share `-ého`).

Value of a unit:  max( Σ OS(form) × scale ,  SNK(lemma) × share(cell kind) )
  OS     OpenSubtitles form frequency: a form list, so it values cells directly; it also finds
         frequent words that hunspell-sk only has as a form of a rare lemma (`tomu` is the
         genitive of `tomus`, `späť` an imperative of `spätiť`),
  scale  OS → SNK median ratio over entries both lists know,
  share  the average share of a paradigm's OS mass this kind of cell carries — a prior for
         forms the subtitles never saw.
Closed classes are kept whole; capitalised stems and acronyms get a 0.25 penalty.

The frequency lists are a SELECTION CRITERION ONLY: no word comes from them.

Measured against whole-entry trimming at the same memory (2026-11-05, held-out text): half
the false positives, but about four times more first suggestions that are another form of the
same word; a larger budget reduces both. See the README.

Usage:
  plan_partial.py --dict data/dictionary.dict --annotations data/annotations.json \
                  --freq data/trimmed/stem_freq.tsv --os sk_full.txt --budget 900000 \
                  -o data/trimmed/keep_entries.tsv --report data/trimmed/report.txt
"""
import argparse
import bz2
import csv
import gzip
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_plan import class_codes, entry_id  # noqa: E402
from expand import expand_word, load_affixes, parse_word_list  # noqa: E402

CLOSED = {"pronoun", "preposition", "conjunction", "particle", "interjection", "number", "numeral"}


def open_text(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    if path.endswith(".bz2"):
        return bz2.open(path, "rt", encoding="utf-8")
    return open(path, encoding="utf-8")


def read_os(path):
    """`<form> <count>` per line (hermitdave/FrequencyWords format)."""
    freq = {}
    with open_text(path) as f:
        for line in f:
            w, _, n = line.rstrip("\n").rpartition(" ")
            if w and n.isdigit():
                freq[w] = freq.get(w, 0) + int(n)
    return freq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dict", required=True)
    ap.add_argument("--annotations", required=True)
    ap.add_argument("--freq", required=True, help="stem_freq.tsv from freq_join.py")
    ap.add_argument("--os", required=True, help="OpenSubtitles form frequency list")
    ap.add_argument("--budget", type=int, required=True, help="distinct word forms")
    ap.add_argument("--proper-penalty", type=float, default=0.25)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--report")
    a = ap.parse_args()

    affixes, _ = load_affixes(a.annotations)
    with open(a.annotations, encoding="utf-8") as f:
        base_md = {k for k, v in json.load(f)["affixes"].items() if v.get("base_metadata")}
    codes = class_codes(a.annotations)
    osf = read_os(a.os)

    snk, os_stem, pos_of = {}, {}, {}
    with open(a.freq, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            s = r["stem"]
            snk[s] = max(snk.get(s, 0), int(r["freq_snk"]))
            os_stem[s] = max(os_stem.get(s, 0), int(r["freq_os"]))
            if r["pos"] and not pos_of.get(s):
                pos_of[s] = r["pos"]
    ratios = sorted(snk[s] / os_stem[s] for s in snk if snk[s] > 0 and os_stem.get(s, 0) > 0)
    scale = ratios[len(ratios) // 2] if ratios else 1.0
    print(f"OpenSubtitles → SNK scale factor (median of overlap): {scale:.2f}", file=sys.stderr)

    def ov(forms):
        return sum(osf.get(x.lower(), 0) for x in forms)

    entries = list(parse_word_list(a.dict))

    # 1. units and the per-kind shares
    units = []                  # (entry index, flags, static forms, kind)
    kind_mass, kind_total = defaultdict(float), defaultdict(float)
    for i, (w, fl) in enumerate(entries):
        S = [c for c in fl if c in affixes and affixes[c]["kind"] != "prefix"]
        P = [c for c in fl if c in affixes and affixes[c]["kind"] == "prefix"]
        exp_f = {f_: expand_word(w, f_, affixes) for f_ in S}
        base_flags = tuple(c for c in S + P if c in base_md) + \
            tuple(f_ for f_ in S if not (exp_f[f_] - {w}) and f_ not in base_md)
        base_forms = expand_word(w, "".join(base_flags), affixes) if base_flags else {w}
        mine = [(i, base_flags, frozenset(base_forms), "base")]
        for f_ in S:
            mine.append((i, (f_,), frozenset(exp_f[f_] - base_forms), f_))
        for p in P:
            ep = expand_word(w, p, affixes)
            mine.append((i, (p,), frozenset(ep - {w}), "p:" + p))
            if affixes[p]["cross"]:
                for f_ in S:
                    if affixes[f_]["cross"]:
                        efp = expand_word(w, f_ + p, affixes)
                        mine.append((i, (f_, p), frozenset(efp - exp_f[f_] - ep), f_ + "|" + p))
        mine = [u for u in mine if u[2]]
        tot = ov(set().union(*(u[2] for u in mine)))
        if tot > 0:
            for u in mine:
                kind_mass[u[3]] += ov(u[2])
                kind_total[u[3]] += tot
        units.extend(mine)
    share = {k: kind_mass[k] / kind_total[k] for k in kind_total if kind_total[k] > 0}

    # 2. value per form of each unit; closed classes first
    def is_proper(w):
        return pos_of.get(w, "") == "acronym" or (w[:1].isupper() and w[:1].isalpha())

    forced, scored = [], []
    for n, (i, _flg, forms, kind) in enumerate(units):
        w = entries[i][0]
        if pos_of.get(w, "") in CLOSED:
            forced.append(n)
            continue
        v = max(ov(forms) * scale, snk.get(w, 0) * share.get(kind, 0.0))
        if is_proper(w):
            v *= a.proper_penalty
        scored.append((v / len(forms), n))
    scored.sort(key=lambda t: -t[0])          # stable: zero-value units keep source order
    order = forced + [n for _, n in scored]

    # 3. greedy on realised marginal cost
    kept, have, used = {}, set(), 0
    for n in order:
        if used >= a.budget:
            break
        i, flg, _forms, _k = units[n]
        w, fl = entries[i]
        cur = kept.get(i)
        new = set(flg) | (cur or set())
        if cur is not None and new == cur:
            continue
        aff = "".join(c for c in fl if c in new)
        props = "".join(c for c in fl if c not in affixes)
        add = expand_word(w, aff + props, affixes) - have
        if used + len(add) > a.budget:
            continue
        kept[i] = new
        have |= add
        used += len(add)

    # 3b. free cells: a class whose forms are all in the build already costs nothing, but it
    # carries morphology. Without it a kept form loses the reading of a dropped homonymous cell
    # (`pomaďarčeného` kept as accusative would lose its genitive), so every kept entry gets
    # every class that adds no new form.
    free = 0
    for i, cur in kept.items():
        w, fl = entries[i]
        props = "".join(c for c in fl if c not in affixes)
        for c in fl:
            if c not in affixes or c in cur:
                continue
            trial = cur | {c}
            aff = "".join(x for x in fl if x in trial)
            if expand_word(w, aff + props, affixes) <= have:
                cur.add(c)
                free += 1
    print(f"free cells added (no new forms): {free:,}", file=sys.stderr)

    by_pos = defaultdict(Counter)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(f"# trim plan · budget {a.budget} distinct word forms · written by plan_partial.py\n"
                f"# word\tentry id\t* whole entry, + only the listed affix classes, - all but the listed\tclass codes\n")
        for i, (w, fl) in enumerate(entries):
            pos = pos_of.get(w, "") or "(none)"
            by_pos[pos]["entries"] += 1
            if i not in kept:
                continue
            all_aff = [c for c in fl if c in affixes]
            eid = entry_id(fl, codes)
            if set(all_aff) <= kept[i]:
                f.write(f"{w}\t{eid}\t*\t\n")
                by_pos[pos]["whole"] += 1
            else:
                keep = sorted(codes[c] for c in all_aff if c in kept[i])
                drop = sorted(codes[c] for c in all_aff if c not in kept[i])
                mode, listed = ("+", keep) if len(keep) <= len(drop) else ("-", drop)
                f.write(f"{w}\t{eid}\t{mode}\t{','.join(listed)}\n")
                by_pos[pos]["partial"] += 1
    whole = sum(c["whole"] for c in by_pos.values())
    partial = sum(c["partial"] for c in by_pos.values())
    lines = [
        f"# Trim plan: budget {a.budget:,} distinct word forms, {used:,} used.",
        f"# Entries kept whole: {whole:,} · kept in part (some paradigm cells only): {partial:,}.",
        "# Distinct forms are what Harper's memory scales with; Harper itself counts slightly",
        "# fewer words, because it folds case (Automattic/harper#2411) — see check_data.py budget.",
        "",
        f"{'pos':12s} {'entries':>8s} {'whole':>8s} {'partial':>8s}",
    ]
    for k in sorted(by_pos, key=lambda k: -by_pos[k]["entries"]):
        c = by_pos[k]
        lines.append(f"{k:12s} {c['entries']:8,} {c['whole']:8,} {c['partial']:8,}")
    report = "\n".join(lines)
    print(report, file=sys.stderr)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            f.write(report + "\n")


if __name__ == "__main__":
    main()
