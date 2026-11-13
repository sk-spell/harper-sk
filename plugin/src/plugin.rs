//! Slovak as a Harper language plugin: the [`LanguagePlugin`] implementation and its WebAssembly
//! exports.

use std::collections::BTreeMap;
use std::sync::Arc;

use harper_core::linting::{FlatConfig, Lint, LintGroup};
use harper_core::parsers::{Markdown, MarkdownOptions, OrgMode, Parser};
use harper_core::spell::{Dictionary, MergedDictionary, MutableDictionary};
use harper_core::{DictWordMetadata, Document, remove_overlaps_map};
use harper_plugin_api::{
    ABI_VERSION, DialectInfo, LanguagePlugin, LintRequest, PluginConfig, PluginInfo, PluginLint,
    Region, export_plugin, lint_to_plugin,
};

use crate::language_detection::{slovak_confidence, slovak_confidence_given_english};
use crate::linting::new_curated_slovak;
use crate::messages::MessageLanguage;
use crate::parsers::PlainSlovak;
use crate::spell::slovak_dictionary;

/// The `harper-core` this plugin is built against; kept in step with `Cargo.toml`.
const HARPER_CORE_VERSION: &str = "3.1.0";

pub struct Slovak {
    base: Arc<dyn Dictionary>,
    /// The dictionary the linters were built with: `base`, plus the user's words.
    dictionary: Arc<MergedDictionary>,
    /// The user's words in `dictionary`, to tell whether a request brings other ones.
    user_words: Vec<String>,
    /// The language the linters in `group` write their messages in.
    messages: MessageLanguage,
    group: LintGroup,
}

impl Slovak {
    fn parser(format: &str) -> Box<dyn Parser> {
        match format {
            "markdown" => Box::new(
                Markdown::with_inline_parser(MarkdownOptions::default(), |source| {
                    PlainSlovak.parse(source)
                })
                .non_english(),
            ),
            "org" => Box::new(
                OrgMode::with_inline_parser(|source| PlainSlovak.parse(source)).non_english(),
            ),
            _ => Box::new(PlainSlovak),
        }
    }

    /// Lint `chars` as `format` and report spans relative to `offset`.
    fn lint_chars(&mut self, chars: &[char], format: &str, offset: usize) -> Vec<PluginLint> {
        let parser = Self::parser(format);
        let document = Document::new_from_chars(chars.to_vec().into(), &parser, &*self.dictionary);

        let mut lints: BTreeMap<String, Vec<Lint>> = self.group.organized_lints(&document);
        remove_overlaps_map(&mut lints);

        lints
            .iter()
            .flat_map(|(rule, lints)| {
                lints.iter().map(move |lint| {
                    let mut lint = lint_to_plugin(lint, rule);
                    lint.span = (lint.span.0 + offset, lint.span.1 + offset);
                    lint
                })
            })
            .collect()
    }

    fn apply_config(&mut self, config: &PluginConfig) {
        for (rule, enabled) in config {
            if let Some(enabled) = enabled
                && self.group.contains_key(rule)
            {
                self.group.config.set_rule_enabled(rule, *enabled);
            }
        }
    }

    /// Rebuild the dictionary and the linters with `words` as the user's words.
    fn use_user_words(&mut self, words: Vec<String>) {
        if words == self.user_words {
            return;
        }
        let mut user = MutableDictionary::new();
        user.extend_words(words.iter().map(|w| {
            (
                w.chars().collect::<Vec<char>>(),
                DictWordMetadata::default(),
            )
        }));

        let mut merged = MergedDictionary::new();
        merged.add_dictionary(self.base.clone());
        merged.add_dictionary(Arc::new(user));
        // The linters hold on to the dictionary, so they are rebuilt with the new one.
        self.dictionary = Arc::new(merged);
        self.user_words = words;
        self.rebuild_linters();
    }

    /// Write the messages for an interface in the language `tag` (BCP 47, such as `en-GB`):
    /// Slovak for a Slovak interface, English for any other. `None`, or a tag that is not one,
    /// goes back to the language of the text.
    ///
    /// Called with [`LintRequest::message_language`] on every request.
    pub fn set_message_language(&mut self, tag: Option<&str>) {
        let language = tag
            .and_then(MessageLanguage::for_interface)
            .unwrap_or_default();
        if language != self.messages {
            self.messages = language;
            self.rebuild_linters();
        }
    }

    /// Build the linters again for the current dictionary and message language, keeping the
    /// rules the user switched off.
    fn rebuild_linters(&mut self) {
        let config: FlatConfig = self.group.config.clone();
        self.group =
            new_curated_slovak(self.dictionary.clone(), self.messages).with_lint_config(config);
    }
}

fn names(names: &[&str]) -> Vec<String> {
    names.iter().map(|n| n.to_string()).collect()
}

impl LanguagePlugin for Slovak {
    fn info() -> PluginInfo {
        PluginInfo {
            id: "sk".into(),
            name: "Slovenčina".into(),
            plugin_version: env!("CARGO_PKG_VERSION").into(),
            abi: ABI_VERSION,
            harper_core_version: HARPER_CORE_VERSION.into(),
            dialects: vec![DialectInfo {
                id: "Standard".into(),
                name: "Slovensko".into(),
                aliases: names(&["Slovakia", "SK", "sk-SK", "sk_SK"]),
            }],
            default_dialect: Some("Standard".into()),
            // What the multilingual build of Harper accepted for Slovak, so its settings keep
            // working.
            aliases: names(&["Slovak", "Slovencina"]),
        }
    }

    fn new() -> Self {
        let base: Arc<dyn Dictionary> = slovak_dictionary();
        let mut merged = MergedDictionary::new();
        merged.add_dictionary(base.clone());
        let dictionary = Arc::new(merged);
        let messages = MessageLanguage::default();
        Self {
            group: new_curated_slovak(dictionary.clone(), messages),
            base,
            dictionary,
            user_words: Vec::new(),
            messages,
        }
    }

    fn lint(&mut self, req: LintRequest) -> Vec<PluginLint> {
        self.set_message_language(req.message_language.as_deref());
        if let Some(words) = req.user_words.clone() {
            self.use_user_words(words);
        }
        if let Some(config) = &req.config {
            self.apply_config(config);
        }

        let chars: Vec<char> = req.text.chars().collect();

        match &req.regions {
            None => self.lint_chars(&chars, &req.format, 0),
            Some(regions) => regions
                .iter()
                .filter(|Region { start, end, .. }| start < end && *end <= chars.len())
                .flat_map(|region| {
                    self.lint_chars(
                        &chars[region.start..region.end],
                        &region.format,
                        region.start,
                    )
                })
                .collect(),
        }
    }

    fn lint_descriptions(&self) -> BTreeMap<String, String> {
        self.group
            .all_descriptions()
            .into_iter()
            .map(|(rule, description)| (rule.to_owned(), description.to_owned()))
            .collect()
    }

    fn default_config(&self) -> PluginConfig {
        self.group
            .iter_keys()
            .map(|rule| (rule.to_owned(), Some(true)))
            .collect()
    }

    fn detect(text: &str, english_ratio: Option<f32>) -> Option<f32> {
        match english_ratio {
            Some(ratio) => slovak_confidence_given_english(text, ratio),
            None => slovak_confidence(text),
        }
    }
}

export_plugin!(Slovak);

#[cfg(test)]
mod tests {
    use harper_plugin_api::{LanguagePlugin, LintRequest};

    use super::Slovak;

    /// Hosts find the plugin by these names, e.g. a harper-ls setting `"dialect": "Slovak"`.
    #[test]
    fn answers_to_its_names_and_dialect() {
        let info = Slovak::info();
        for name in ["sk", "Slovenčina", "slovak", "Slovensko", "sk-SK", "SK"] {
            assert!(info.answers_to(name), "{name}");
        }
        assert!(!info.answers_to("German"));
    }

    #[test]
    fn user_words_in_the_request_are_not_flagged() {
        let mut plugin = Slovak::new();
        let text = "Dohodli sa s firmou Qwyrtex.";
        let flagged = |plugin: &mut Slovak, req: LintRequest| {
            plugin
                .lint(req)
                .into_iter()
                .any(|l| l.rule == "SlovakSpellCheck")
        };
        assert!(flagged(&mut plugin, LintRequest::plain(text)));
        let mut req = LintRequest::plain(text);
        req.user_words = Some(vec!["Qwyrtex".into()]);
        assert!(!flagged(&mut plugin, req));
    }

    #[test]
    fn messages_follow_the_interface_language() {
        let mut plugin = Slovak::new();
        let text = "Sme stastni. v dnes je pekný deň.";
        let messages = |plugin: &mut Slovak, language: Option<&str>| -> Vec<String> {
            let mut req = LintRequest::plain(text);
            req.message_language = language.map(str::to_owned);
            let mut lints = plugin.lint(req);
            lints.sort_by_key(|l| l.span);
            lints.into_iter().map(|l| l.message).collect()
        };

        let slovak = messages(&mut plugin, None);
        assert_eq!(slovak.len(), 2, "{slovak:?}");
        assert!(slovak[0].starts_with("Slovo „stastni“"), "{slovak:?}");
        assert!(slovak[1].starts_with("Správne je"), "{slovak:?}");

        let english = messages(&mut plugin, Some("en-GB"));
        assert!(english[0].starts_with("The word “stastni”"), "{english:?}");
        assert!(
            english[1].starts_with("The correct phrase is"),
            "{english:?}"
        );

        assert_eq!(messages(&mut plugin, Some("sk")), slovak);
        assert_eq!(messages(&mut plugin, None), slovak);
    }

    #[test]
    fn switching_the_message_language_keeps_rules_switched_off() {
        let mut plugin = Slovak::new();
        let mut req = LintRequest::plain("v dnes je pekný deň.");
        req.config = Some([("VDnes".to_string(), Some(false))].into_iter().collect());
        assert!(plugin.lint(req).iter().all(|l| l.rule != "VDnes"));
        let mut req = LintRequest::plain("v dnes je pekný deň.");
        req.message_language = Some("en".into());
        assert!(plugin.lint(req).iter().all(|l| l.rule != "VDnes"));
    }
}
