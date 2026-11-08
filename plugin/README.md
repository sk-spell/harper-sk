# harper-sk.wasm: Slovak for Harper as a language plugin

Slovak spell checking for [Harper](https://github.com/Automattic/harper), built as one WebAssembly
file that Harper's language plugin host loads (`harper-ls`, `harper-cli`, the browser extension,
Obsidian). The plugin system is Dronakurl's (Dronakurl/harper#14, branch
`feature/language-plugins`); this crate follows the German plugin,
[harper-german](https://github.com/Dronakurl/harper-german). How plugins are installed and
loaded is described on the
[language plugins page](https://github.com/Dronakurl/harper/blob/feature/language-plugins/packages/web/src/routes/docs/integrations/language-plugins/%2Bpage.md).

The words come from [hunspell-sk](https://github.com/sk-spell/hunspell-sk) through the generator
in this repository (`../scripts/`, `../data/`, MPL-2.0); the plugin code is Apache-2.0.

## What it does

- `SlovakSpellCheck`: flags words that are not in the dictionary and suggests corrections, ranked
  with the hunspell-sk suggestion hints (REP, MAP, KEY, TRY) in `../data/annotations.json`.
- Weir rules in `src/linting/weir_rules/` (one example so far).
- Every message exists in Slovak and English (`src/messages.rs`; a Weir rule carries
  `messageSk` next to `message`). They are Slovak, the language of the text, until the host
  passes the language of its interface, which the plugin API cannot do yet; then a Slovak
  interface gets Slovak messages and any other interface English ones.
- Language detection (`detect_with`): Slovak letters (ľ, ĺ, ŕ, ô, and ä next to another Slovak
  letter) answer 0.97, letters shared with Czech 0.9, common Slovak words 0.85 or 0.6. Czech and
  Polish letters rule Slovak out.

## Building

```bash
just test          # native tests
just bake-pack     # expand the word list into pack/slovak.pack (baked into the module)
just test-plugin   # build the module and load it through harper-plugin-host
just release-files 0.1.0
```

`build.rs` reads `../data/trimmed/dictionary.dict` (the `full` feature: `../data/dictionary.dict`)
and `../data/annotations.json`, or the directory in `SK_DATA_DIR`. A pack is used only if it was
baked from exactly these data and this code; otherwise the dictionary is expanded at first use.

Measured on 8 November 2026 (trimmed list, 900,007 word forms): the module is 43.9 MB, the
first load compiles it in about 2 s (then cached), and the first check after loading takes
0.2 s.

## Known differences from the built-in module

- The dictionary is `CompactDictionary` from harper-german, which keeps the Slovak word forms in
  about a third of the memory of `FstDictionary`.
- The morphology (case, number, gender) in the data is not yet carried into Harper's
  `LanguageBits`; spell checking does not need it, grammar rules will.
- Words that differ only in case ("se" and "Se") are suggested once.
- The English lexer splits "usídli" into "us" and "ídli" (Automattic/harper#774); the Slovak
  lexer reads such words whole.
