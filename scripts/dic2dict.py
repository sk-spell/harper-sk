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
"""
dic2dict.py — preloží hunspell sk_SK.dic → Harper dictionary.dict (kmene + flagy).

Vstupný riadok hunspellu:   kmeň[/AFIXFLAGY][\t| ]po:noun is:feminine
Výstupný riadok Harpera:    kmeň/<AFIXFLAGY><POSFLAG>

POS flagy musia zodpovedať `properties` v annotations.json (viď aff2annotations.POS_FLAG).
Prvý riadok výstupu = počet záznamov (hunspell konvencia, Harper ju akceptuje).

Voliteľné orezanie pokrytia (variant „B"): --keep-stems <súbor s lemami> alebo --limit N.

Použitie: dic2dict.py <sk_SK.dic> [-o dictionary.dict] [--keep-stems f] [--limit N]
"""
import argparse, re, sys
from collections import Counter

# musí sedieť s aff2annotations.POS_FLAG
POS_FLAG = {
    'noun': 'a', 'verb': 'e', 'adjective': 'd', 'adverb': 'f',
    'pronoun': 'g', 'preposition': 'h', 'conjunction': 'i',
    'interjection': 'j', 'particle': 'k', 'number': 'l',
    'acronym': 'm', 'participle': 'o',
    'adjectiv': 'd',   # preklep v zdrojovom sk_SK.dic (1×)
}
POS_RE = re.compile(r'\bpo:([a-z_]+)')

# Licenčná hlavička generovaných dát. Harper `parse_word_list` preskakuje riadky
# začínajúce '#', ale PRVÝ riadok musí byť počet záznamov → hlavička ide až pod neho.
# (overené: harper-core/src/spell/rune/word_list.rs:24-28)
DATA_HEADER = """\
Slovak dictionary data for Harper — word list.
Derived from sk-spell/hunspell-sk <https://github.com/sk-spell/hunspell-sk>
by Zdenko Podobný and contributors.

SPDX-License-Identifier: MPL-2.0
This Source Code Form is subject to the terms of the Mozilla Public License,
v. 2.0. If a copy of the MPL was not distributed with this file, You can
obtain one at <https://mozilla.org/MPL/2.0/>.

GENERATED FILE — do not edit by hand. Rebuild with scripts/dic2dict.py.
Source revision: {rev}"""


def parse_dic(path):
    """Vygeneruje (kmeň, afix_flagy, pos) pre každý záznam."""
    with open(path, encoding='utf-8') as f:
        lines = f.read().splitlines()
    # 1. riadok = počet (ak je to číslo)
    if lines and lines[0].strip().isdigit():
        lines = lines[1:]
    for ln in lines:
        if not ln.strip() or ln.lstrip().startswith('#'):
            continue
        # oddeľ morfologickú časť (za tabom alebo za medzerou nasledovanou po:/is:)
        head = re.split(r'[\t ]', ln, maxsplit=1)
        word_part = head[0]
        morph = head[1] if len(head) > 1 else ''
        if '/' in word_part:
            stem, flags = word_part.split('/', 1)
        else:
            stem, flags = word_part, ''
        m = POS_RE.search(morph)
        yield stem.strip(), flags.strip(), (m.group(1) if m else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dic')
    ap.add_argument('-o', '--out', default='dictionary.dict')
    ap.add_argument('--keep-stems', help='súbor so zoznamom lem, ktoré ponechať (variant B)')
    ap.add_argument('--limit', type=int, help='ponechaj len prvých N záznamov (test)')
    ap.add_argument('--no-pos', action='store_true', help='nepridávaj POS flagy (čistý spell test)')
    ap.add_argument('--source-rev', default='unknown',
                    help='revízia zdrojového hunspell-sk (zapíše sa do hlavičky)')
    a = ap.parse_args()

    keep = None
    if a.keep_stems:
        with open(a.keep_stems, encoding='utf-8') as f:
            keep = {l.strip() for l in f if l.strip()}

    stats = Counter()
    out = []
    for i, (stem, flags, pos) in enumerate(parse_dic(a.dic)):
        if a.limit and i >= a.limit:
            break
        if keep is not None and stem not in keep:
            stats['skipped_by_keep'] += 1
            continue
        if not stem:
            continue
        pos_flag = '' if a.no_pos else POS_FLAG.get(pos or '', '')
        if pos and pos not in POS_FLAG:
            stats[f'unknown_pos:{pos}'] += 1
        all_flags = flags + pos_flag
        out.append(f"{stem}/{all_flags}" if all_flags else stem)
        stats['written'] += 1

    with open(a.out, 'w', encoding='utf-8') as f:
        f.write(f"{len(out)}\n")          # počet MUSÍ byť prvý riadok
        for line in DATA_HEADER.format(rev=a.source_rev).split('\n'):
            f.write(f"# {line}\n" if line else "#\n")
        f.write("\n".join(out) + "\n")

    print(f"zapísaných záznamov: {stats['written']}", file=sys.stderr)
    for k, v in stats.items():
        if k != 'written':
            print(f"  {k}: {v}", file=sys.stderr)
    print(f"→ {a.out}", file=sys.stderr)


if __name__ == '__main__':
    main()
