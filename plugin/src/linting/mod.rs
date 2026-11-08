//! Slovak linters.

pub mod slovak_spell_check;
pub mod weir_rules;

use std::sync::Arc;

use harper_core::linting::LintGroup;
use harper_core::spell::Dictionary;

use slovak_spell_check::SlovakSpellCheck;

use crate::messages::MessageLanguage;

/// Every Slovak linter, all enabled, checking words against `dictionary` and writing its
/// messages in `language`.
pub fn new_curated_slovak(
    dictionary: Arc<impl Dictionary + 'static>,
    language: MessageLanguage,
) -> LintGroup {
    let mut group = LintGroup::empty();
    group.merge_from(weir_rules::lint_group(language));
    group.add(
        "SlovakSpellCheck",
        SlovakSpellCheck::in_language(dictionary, language),
    );
    group.set_all_rules_to(Some(true));
    group
}
