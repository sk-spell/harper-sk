//! The suggestions the built plugin gives for a list of typos, through `harper-plugin-host`.
//!
//! stdin: `kind \t correct \t typo` per line (the 633 typos of the Slovak measurements);
//! stdout: the same line + `\t` the first five suggestions, comma-separated.
//! Build the module first (`just build-wasm`).

use std::io::BufRead;

use harper_plugin_api::{LintRequest, PluginSuggestion};
use harper_plugin_host::PluginHost;

fn main() {
    let path = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "target/wasm32-unknown-unknown/release/harper_sk.wasm".into());
    let host = PluginHost::new().unwrap();
    let plugin = host
        .load_file_cached(&path, std::env::temp_dir().join("harper-sk-test-cache"))
        .unwrap();
    for line in std::io::stdin().lock().lines() {
        let line = line.unwrap();
        let typo = line.split('\t').nth(2).unwrap();
        let lints = plugin.lint(&LintRequest::plain(typo)).unwrap();
        let top: Vec<String> = lints
            .iter()
            .find(|l| l.rule == "SlovakSpellCheck")
            .map(|l| {
                l.suggestions
                    .iter()
                    .filter_map(|s| match s {
                        PluginSuggestion::ReplaceWith(w) => Some(w.clone()),
                        _ => None,
                    })
                    .collect()
            })
            .unwrap_or_default();
        println!("{line}\t{}", top.join(","));
    }
}
