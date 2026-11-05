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
"""apply_plan.py — cut the full word list down to a trim plan.

The trim plan (`data/trimmed/keep_entries.tsv`, written by `plan_partial.py`) says, entry by
entry, which affix classes stay. Applying it needs no frequency lists, so the weekly rebuild
can keep the trimmed build in step with hunspell-sk (`make retrim`).

Plan format, one kept entry per line:

    <word> TAB <entry id> TAB * | + | - TAB <class codes, comma separated>

  `*`  the whole entry stays,
  `+`  only the listed classes stay (a partial paradigm),
  `-`  all classes but the listed ones stay (the same, written the shorter way round);
  property flags always stay.

Affix classes are named by a *class code*, a short hash of the class description in
annotations.json, not by their flag character. With `--morphology full` the converter numbers
the sub-classes into the private-use area, and that numbering may shift when the affix file
changes; the description (`sk affix class z — case: Genitive, …`) does not. The entry id is
the hash of the codes of all the entry's affix classes, which tells homographs apart. Entries
the source no longer has, or whose classes changed, simply drop — as with the old keep list,
a later `make trim` picks them up again.

Usage: apply_plan.py data/dictionary.dict data/annotations.json data/trimmed/keep_entries.tsv \
           -o data/trimmed/dictionary.dict
"""
import argparse
import hashlib
import json
import sys


def class_codes(annotations_path):
    """flag character -> class code, for every affix class; exits on a code collision."""
    with open(annotations_path, encoding="utf-8") as f:
        affixes = json.load(f)["affixes"]
    codes = {}
    for flag, a in affixes.items():
        label = a.get("#") or f"{a['kind']}:{flag}"
        codes[flag] = hashlib.sha1(label.encode("utf-8")).hexdigest()[:6]
    if len(set(codes.values())) != len(codes):
        sys.exit("class codes collide — lengthen the hash in apply_plan.class_codes")
    return codes


def entry_id(flags, codes):
    return hashlib.sha1(",".join(sorted(codes[c] for c in flags if c in codes))
                        .encode("utf-8")).hexdigest()[:8]


def read_lines(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    header = [l for l in lines[1:] if l.startswith("#")]
    body = [l for l in lines[1:] if l and not l.startswith("#")]
    return header, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dictionary")
    ap.add_argument("annotations")
    ap.add_argument("plan")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    codes = class_codes(a.annotations)
    plan = {}
    with open(a.plan, encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            word, eid, mode, keep = (line.rstrip("\n").split("\t") + [""])[:4]
            listed = set(filter(None, keep.split(",")))
            plan[(word, eid)] = None if mode == "*" else (mode, listed)

    header, body = read_lines(a.dictionary)
    header = [("# GENERATED FILE — do not edit by hand. Trimmed from data/dictionary.dict by "
               "scripts/apply_plan.py (make trim / make retrim).") if l.startswith("# GENERATED FILE")
              else l for l in header]
    out = []
    for line in body:
        word, _, flags = line.partition("/")
        keep = plan.get((word, entry_id(flags, codes)), False)
        if keep is False:
            continue
        if keep is not None:
            mode, listed = keep
            flags = "".join(c for c in flags if c not in codes
                            or (codes[c] in listed) == (mode == "+"))
        out.append(f"{word}/{flags}" if flags else word)

    with open(a.out, "w", encoding="utf-8") as f:
        f.write(f"{len(out)}\n")
        f.write("\n".join(header) + "\n")
        f.write("\n".join(out) + "\n")
    print(f"{len(out):,} of {len(plan):,} planned entries found in the source → {a.out}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
