//! Loads the built `harper_sk.wasm` through `harper-plugin-host`, the way `harper-ls` does.
//!
//! Build it first: `just build-wasm`. Without the module these tests do nothing locally and
//! fail in CI, where it must exist.

use std::path::PathBuf;
use std::time::Instant;

use harper_plugin_api::{LintRequest, PluginSuggestion, Region};
use harper_plugin_host::{LoadedPlugin, PluginHost};

fn wasm_path() -> PathBuf {
    std::env::var_os("HARPER_SK_WASM")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("target/wasm32-unknown-unknown/release/harper_sk.wasm")
        })
}

fn load() -> Option<LoadedPlugin> {
    let path = wasm_path();
    if !path.exists() {
        assert!(
            std::env::var_os("CI").is_none(),
            "{} must exist in CI",
            path.display()
        );
        eprintln!(
            "skipping: {} does not exist (run `just build-wasm`)",
            path.display()
        );
        return None;
    }

    let host = PluginHost::new().unwrap();
    let cache = std::env::temp_dir().join("harper-sk-test-cache");
    let t = Instant::now();
    let plugin = host.load_file_cached(&path, &cache).unwrap();
    eprintln!("load (compile + instantiate): {:?}", t.elapsed());
    Some(plugin)
}

fn replacements(suggestions: &[PluginSuggestion]) -> Vec<&str> {
    suggestions
        .iter()
        .filter_map(|s| match s {
            PluginSuggestion::ReplaceWith(w) => Some(w.as_str()),
            _ => None,
        })
        .collect()
}

#[test]
fn reports_what_it_is() {
    let Some(plugin) = load() else { return };
    let info = plugin.info();
    assert_eq!(info.id, "sk");
    assert_eq!(info.name, "Slovenčina");
    assert_eq!(info.abi, 1);
    assert!(
        plugin
            .lint_descriptions()
            .unwrap()
            .contains_key("SlovakSpellCheck")
    );
    assert!(
        plugin
            .default_config()
            .unwrap()
            .contains_key("SlovakSpellCheck")
    );
}

#[test]
fn finds_a_misspelling_and_suggests_the_fix() {
    let Some(plugin) = load() else { return };
    let t = Instant::now();
    let lints = plugin
        .lint(&LintRequest::plain("Sme stastni, že sme doma."))
        .unwrap();
    eprintln!("first lint: {:?}", t.elapsed());

    let spell = lints
        .iter()
        .find(|l| l.rule == "SlovakSpellCheck")
        .expect("a spelling lint");
    assert_eq!(spell.span, (4, 11));
    assert_eq!(
        replacements(&spell.suggestions).first().copied(),
        Some("šťastní"),
        "{spell:?}"
    );
    assert!(spell.message.starts_with("Slovo „stastni“"), "{spell:?}");

    let t = Instant::now();
    plugin
        .lint(&LintRequest::plain("Ďalšia veta bez chyby."))
        .unwrap();
    eprintln!("second lint: {:?}", t.elapsed());
}

#[test]
fn correct_slovak_gives_no_spelling_lints() {
    let Some(plugin) = load() else { return };
    let lints = plugin
        .lint(&LintRequest::plain(
            "Vďaka tomu sa vrátil späť. Zrejme konečne prišlo päť rokov.",
        ))
        .unwrap();
    assert!(
        lints.iter().all(|l| l.rule != "SlovakSpellCheck"),
        "{lints:?}"
    );
}

#[test]
fn a_weir_rule_runs() {
    let Some(plugin) = load() else { return };
    let lints = plugin
        .lint(&LintRequest::plain("v dnes je pekný deň."))
        .unwrap();
    assert!(lints.iter().any(|l| l.rule == "VDnes"), "{lints:?}");
}

#[test]
fn regions_report_spans_in_the_whole_text() {
    let Some(plugin) = load() else { return };
    let text = "```\nkod\n```\nSme stastni.";
    let start = text.chars().position(|c| c == 'S').unwrap();
    let mut req = LintRequest::plain(text);
    req.regions = Some(vec![Region {
        start,
        end: text.chars().count(),
        format: "plain".into(),
    }]);
    let lints = plugin.lint(&req).unwrap();
    let spell = lints
        .iter()
        .find(|l| l.rule == "SlovakSpellCheck")
        .expect("a spelling lint");
    assert_eq!(spell.span, (start + 4, start + 11));
}

#[test]
fn detects_slovak_and_not_english() {
    let Some(plugin) = load() else { return };
    let sk = plugin
        .detect("Vďaka tomu sa vrátil späť. Zrejme konečne prišlo päť rokov.")
        .unwrap();
    assert!(sk.is_some_and(|c| c > 0.95), "{sk:?}");
    let en = plugin
        .detect("I am happy in the house. You are tired at school. He is at work.")
        .unwrap();
    assert_eq!(en, None);
}
