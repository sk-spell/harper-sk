//! Lint a text natively with the plugin and print every lint.
use harper_plugin_api::{LanguagePlugin, LintRequest};
fn main() {
    let mut p = harper_sk::plugin::Slovak::new();
    for t in std::env::args().skip(1) {
        for l in p.lint(LintRequest::plain(t.clone())) {
            println!("{t:?}: {} {:?} {}", l.rule, l.span, l.message);
        }
    }
}
