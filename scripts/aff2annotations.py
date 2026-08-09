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
aff2annotations.py — translate hunspell sk_SK.aff into Harper annotations.json.

Mapping (hunspell → Harper):
    SFX/PFX <flag> Y|N <count>          → affixes[<flag>].kind = suffix|prefix,
                                          cross_product = (Y == true)
    SFX <flag> <remove> <add> <cond> …  → replacements[] {remove, add, condition}
    "0"                                  → "" (hunspell's zero means empty string)
    <add>/<cont>                         → the continuation flag is stripped (Harper has
                                          no concept of it) and counted in the stats
    po:<pos> on a rule                   → target[].metadata (part of speech of the result)

A note on CIRCUMFIX: sk_SK.aff declares `CIRCUMFIX s`, and flag `s` appears as a
continuation on PFX F (naj-/najne-). Harper does not support circumfixes, so those
rules are flagged here and handled by the equivalence test, not by this script.

Usage: aff2annotations.py <sk_SK.aff> [-o annotations.json] [--stats]
"""
import argparse, json, re, sys
from collections import OrderedDict, Counter

# hunspell po: → Harper `DictWordMetadata` (authoritative: harper-core/src/dict_word_metadata.rs).
# ⚠️ Mind the types: noun/pronoun/verb/adjective/adverb/conjunction/determiner are
# Option<...Data> (i.e. a MAP), but `preposition` is a plain `bool`. Harper has NO fields
# for interjection/particle/numeral/acronym — those go through the generic
# `pos_tag: Option<UPOS>` (variants in harper-pos-utils/src/upos.rs: ADJ ADP ADV AUX CCONJ
#  DET INTJ NOUN NUM PART PRON PROPN PUNCT SCONJ SYM VERB X).
POS_MAP = {
    'noun':         {'noun': {}},
    'verb':         {'verb': {}},
    'adjective':    {'adjective': {}},
    'adverb':       {'adverb': {}},
    'pronoun':      {'pronoun': {}},
    'conjunction':  {'conjunction': {}},
    'preposition':  {'preposition': True},              # a bool, NOT a map
    'interjection': {'pos_tag': 'INTJ'},
    'particle':     {'pos_tag': 'PART'},
    'number':       {'pos_tag': 'NUM'},
    'acronym':      {'noun': {'is_proper': True}, 'pos_tag': 'PROPN'},
    'participle':   {'verb': {}},
    'adjectiv':     {'adjective': {}},                  # typo in the source sk_SK.dic (once)
}

# Licence header for the generated data. JSON has no comments, but Harper deserializes
# `HumanReadableAttributeList` without `deny_unknown_fields`, so an unknown top-level
# key "#" is silently ignored by serde.
# (verified: harper-core/src/spell/rune/attribute_list.rs:275-279)
DATA_HEADER = [
    "Slovak dictionary data for Harper — affix annotations.",
    "Derived from sk-spell/hunspell-sk <https://github.com/sk-spell/hunspell-sk>",
    "by Zdenko Podobný and contributors.",
    "SPDX-License-Identifier: MPL-2.0",
    "This Source Code Form is subject to the terms of the Mozilla Public License,",
    "v. 2.0. If a copy of the MPL was not distributed with this file, You can",
    "obtain one at <https://mozilla.org/MPL/2.0/>.",
    "GENERATED FILE — do not edit by hand. Rebuild with scripts/aff2annotations.py.",
]

HEADER_RE = re.compile(r'^(SFX|PFX)\s+(\S+)\s+([YN])\s+(\d+)')
TAG_RE = re.compile(r'\b(po|is|ts|tp):([a-z_0-9]+)')


def parse_aff(path):
    """Return (affixes_raw, stats). affixes_raw: flag → dict(kind, cross, rules[])."""
    affixes = OrderedDict()
    stats = Counter()
    current = None
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')
            if not line or line.lstrip().startswith('#'):
                continue
            m = HEADER_RE.match(line)
            if m:
                kind_tok, flag, cross, _cnt = m.groups()
                current = flag
                affixes[flag] = {
                    'kind': 'suffix' if kind_tok == 'SFX' else 'prefix',
                    'cross_product': cross == 'Y',
                    'rules': [],
                    'comment': line.split('#', 1)[1].strip() if '#' in line else '',
                }
                continue
            # a rule line
            parts = line.split('#', 1)[0].split()
            if len(parts) < 4 or parts[0] not in ('SFX', 'PFX'):
                continue
            flag = parts[1]
            if flag not in affixes:
                stats['rule_without_header'] += 1
                continue
            remove, add, cond = parts[2], parts[3], parts[4] if len(parts) > 4 else '.'
            tags = TAG_RE.findall(' '.join(parts[4:]))
            # continuation flag inside add:  "naj/s" → add="naj", cont="s"
            cont = ''
            if '/' in add:
                add, cont = add.split('/', 1)
                stats['continuation_flags'] += 1
            affixes[flag]['rules'].append({
                'remove': '' if remove == '0' else remove,
                'add': '' if add == '0' else add,
                'condition': cond,
                'tags': tags,
                'cont': cont,
            })
            stats['rules'] += 1
    return affixes, stats


def target_from_tags(rules):
    """If every rule in the class agrees on a part of speech, put it in target."""
    poss = {t[1] for r in rules for t in r['tags'] if t[0] == 'po'}
    if len(poss) == 1:
        pos = poss.pop()
        if pos in POS_MAP:
            return [{'metadata': dict(POS_MAP[pos])}]
    return []


def build_annotations(affixes, source_rev='unknown'):
    out_aff = OrderedDict()
    for flag, a in affixes.items():
        out_aff[flag] = OrderedDict([
            ('#', a['comment'] or f"sk affix class {flag}"),
            ('kind', a['kind']),
            ('cross_product', a['cross_product']),
            ('replacements', [
                OrderedDict([('remove', r['remove']),
                             ('add', r['add']),
                             ('condition', r['condition'])])
                for r in a['rules']
            ]),
            ('target', target_from_tags(a['rules'])),
            ('base_metadata', {}),
            ('rename_ok', True),
        ])
    # properties: part-of-speech flags used in dictionary.dict (see dic2dict.py)
    props = OrderedDict()
    for pos, meta in POS_MAP.items():
        flag = POS_FLAG.get(pos)
        if flag and flag not in props:
            props[flag] = OrderedDict([
                ('#', f'{pos} property (Slovak)'),
                ('metadata', dict(meta)),
            ])
    return OrderedDict([
        ('#', DATA_HEADER + [f'Source revision: {source_rev}']),
        ('affixes', out_aff),
        ('properties', props),
    ])


# Part-of-speech flags used in dictionary.dict.
# ⚠️ These MUST NOT collide with the affix flags of sk_SK.aff, which are:
#     upper case: N F Z U D K M S V A C H B J L O Q Y I P X E W T R
#     lower case: z c q b n
#     plus 's', reserved for CIRCUMFIX
# Free, and used here: a d e f g h i j k l m o
POS_FLAG = {
    'noun': 'a', 'verb': 'e', 'adjective': 'd', 'adverb': 'f',
    'pronoun': 'g', 'preposition': 'h', 'conjunction': 'i',
    'interjection': 'j', 'particle': 'k', 'number': 'l',
    'acronym': 'm', 'participle': 'o',
    'adjectiv': 'd',   # typo in the source → same flag as adjective
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('aff')
    ap.add_argument('-o', '--out', default='annotations.json')
    ap.add_argument('--stats', action='store_true')
    ap.add_argument('--source-rev', default='unknown',
                    help='revision of the hunspell-sk source (recorded in the header)')
    a = ap.parse_args()

    affixes, stats = parse_aff(a.aff)
    # do the affix flags and the POS flags collide?
    clash = set(affixes) & set(POS_FLAG.values())
    if clash:
        print(f"⚠️  affix×POS flag COLLISION: {sorted(clash)} — adjust POS_FLAG!", file=sys.stderr)

    ann = build_annotations(affixes, a.source_rev)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(ann, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print(f"affix classes: {len(ann['affixes'])}  properties: {len(ann['properties'])}", file=sys.stderr)
    print(f"rules: {stats['rules']}  continuation flags: {stats['continuation_flags']}", file=sys.stderr)
    if a.stats:
        for flag, x in affixes.items():
            print(f"  {flag} {x['kind'][:3]} cross={'Y' if x['cross_product'] else 'N'} "
                  f"rules={len(x['rules'])} {x['comment'][:40]}", file=sys.stderr)
    print(f"→ {a.out}", file=sys.stderr)


if __name__ == '__main__':
    main()
