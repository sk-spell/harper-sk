//! Slovak spell check.

use harper_core::linting::{Lint, LintKind, Linter, Suggestion};
use harper_core::spell::{Dictionary, SuggestionHints, suggest_correct_spelling_with_hints};
use harper_core::{Document, TokenStringExt};

use crate::spell::slovak_suggestion_hints;

/// Flags words that are not in the Slovak dictionary and suggests corrections, ranked with the
/// hunspell-sk suggestion hints.
pub struct SlovakSpellCheck<T>
where
    T: Dictionary,
{
    dictionary: T,
    hints: &'static SuggestionHints,
}

impl<T: Dictionary> SlovakSpellCheck<T> {
    pub fn new(dictionary: T) -> Self {
        Self {
            dictionary,
            hints: slovak_suggestion_hints(),
        }
    }

    /// The most suggestions offered for one word.
    const MAX_SUGGESTIONS: usize = 5;

    /// How many edit-distance matches are ranked. `fuzzy_match` cuts its results in code point
    /// order, so a small limit drops words with diacritics ("ťo" would never get "to" or "čo").
    const CANDIDATE_LIMIT: usize = 200;

    /// Spelling suggestions for a word, ranked with the Slovak suggestion hints (REP, MAP, KEY,
    /// TRY) imported from hunspell-sk.
    fn get_suggestions(&self, word: &[char]) -> Vec<Vec<char>> {
        let ranked = suggest_correct_spelling_with_hints(
            word,
            Self::CANDIDATE_LIMIT,
            2,
            &self.dictionary,
            self.hints,
        );
        let suggestions = merge_case_variants(word, ranked)
            .into_iter()
            .take(Self::MAX_SUGGESTIONS)
            .collect();

        match_capitalization(word, suggestions)
    }
}

/// One suggestion per word, whatever its capitalization.
///
/// The dictionary keeps spellings that differ only in case as separate words ("se" and "Se",
/// "jel" and the name "Jel"), and both would take a place among the few suggestions shown.
/// Each word keeps the place of its best-ranked spelling and takes the lowercase spelling when
/// the writer typed lowercase (as the German plugin does).
fn merge_case_variants(word: &[char], ranked: Vec<&[char]>) -> Vec<Vec<char>> {
    let lower_initial = |w: &[char]| w.first().is_some_and(|c| c.is_lowercase());
    let mut out: Vec<Vec<char>> = Vec::new();
    for candidate in ranked {
        let folded: Vec<char> = candidate.iter().flat_map(|c| c.to_lowercase()).collect();
        let same = out.iter_mut().find(|kept| {
            kept.iter()
                .flat_map(|c| c.to_lowercase())
                .eq(folded.iter().copied())
        });
        match same {
            Some(kept) => {
                if lower_initial(word) && lower_initial(candidate) && !lower_initial(kept) {
                    *kept = candidate.to_vec();
                }
            }
            None => out.push(candidate.to_vec()),
        }
    }
    out
}

/// Carry the misspelled word's capitalization over to the suggestions.
///
/// The dictionary stores most words in lowercase, so without this a word capitalized at the
/// start of a sentence ("Nezavisle") would be corrected to a lowercase word ("nezávisle"). An
/// all-uppercase word ("NEZAVISLE") gets all-uppercase suggestions. A suggestion with a capital
/// letter after its first character has its own fixed capitalization and is left alone, as in
/// the English spell check. Suggestions that become identical are merged.
fn match_capitalization(word: &[char], suggestions: Vec<Vec<char>>) -> Vec<Vec<char>> {
    let Some(first) = word.first() else {
        return suggestions;
    };

    let all_uppercase = word.len() > 1 && word.iter().all(|c| !c.is_lowercase());
    if !first.is_uppercase() {
        return suggestions;
    }

    let mut out: Vec<Vec<char>> = Vec::with_capacity(suggestions.len());
    for mut suggestion in suggestions {
        let has_internal_caps = suggestion.iter().skip(1).any(|c| c.is_uppercase());
        if all_uppercase {
            suggestion = suggestion.iter().flat_map(|c| c.to_uppercase()).collect();
        } else if !has_internal_caps && let Some(f) = suggestion.first_mut() {
            *f = f.to_uppercase().next().unwrap_or(*f);
        }
        if !out.contains(&suggestion) {
            out.push(suggestion);
        }
    }
    out
}

impl<T: Dictionary> Linter for SlovakSpellCheck<T> {
    fn lint(&mut self, document: &Document) -> Vec<Lint> {
        let mut lints = Vec::new();

        for paragraph in document.iter_paragraphs() {
            for sentence in paragraph.iter_sentences() {
                for word in sentence.iter_words() {
                    let word_chars = document.get_span_content(&word.span);

                    if self.dictionary.contains_word(word_chars) {
                        continue;
                    }

                    let suggestions = self.get_suggestions(word_chars);
                    let word_str: String = word_chars.iter().collect();

                    let message = if suggestions.is_empty() {
                        format!("Slovo „{word_str}“ nie je v slovníku.")
                    } else {
                        let listed: Vec<String> = suggestions
                            .iter()
                            .map(|s| s.iter().collect::<String>())
                            .collect();
                        format!(
                            "Slovo „{word_str}“ môže byť napísané nesprávne. Mysleli ste: {}?",
                            listed.join(", ")
                        )
                    };

                    lints.push(Lint {
                        span: word.span,
                        lint_kind: LintKind::Spelling,
                        suggestions: suggestions
                            .into_iter()
                            .map(Suggestion::ReplaceWith)
                            .collect(),
                        priority: 20,
                        message,
                    });
                }
            }
        }

        lints
    }

    fn description(&self) -> &str {
        "Checks for spelling errors in Slovak text"
    }
}

#[cfg(test)]
mod tests {
    use harper_core::Document;
    use harper_core::linting::Linter;

    use super::{SlovakSpellCheck, match_capitalization, merge_case_variants};
    use crate::parsers::PlainSlovak;
    use crate::spell::{slovak_dictionary, slovak_suggestion_hints};

    fn chars(s: &str) -> Vec<char> {
        s.chars().collect()
    }

    fn strings(words: Vec<Vec<char>>) -> Vec<String> {
        words.into_iter().map(|w| w.into_iter().collect()).collect()
    }

    fn suggestions_for(word: &str) -> Vec<String> {
        let check = SlovakSpellCheck::new(slovak_dictionary());
        strings(check.get_suggestions(&chars(word)))
    }

    fn spell_check_messages(text: &str) -> Vec<String> {
        let dictionary = slovak_dictionary();
        let document = Document::new(text, &PlainSlovak, &*dictionary);
        let mut check = SlovakSpellCheck::new(dictionary.clone());
        check
            .lint(&document)
            .into_iter()
            .map(|lint| lint.message)
            .collect()
    }

    #[test]
    fn diacritic_variant_comes_first() {
        // Reported by the hunspell-sk maintainer: "ťo" used to get "bo, do, ho, io, no".
        let suggestions = suggestions_for("ťo");
        assert_eq!(
            suggestions.first().map(String::as_str),
            Some("to"),
            "got {suggestions:?}"
        );
        assert!(
            suggestions.contains(&"čo".to_string()),
            "got {suggestions:?}"
        );
    }

    #[test]
    fn missing_diacritic_is_restored() {
        let suggestions = suggestions_for("chraniť");
        assert_eq!(
            suggestions.first().map(String::as_str),
            Some("chrániť"),
            "got {suggestions:?}"
        );
    }

    #[test]
    fn word_typed_without_any_diacritics_is_found() {
        // Three edits away, beyond the edit-distance search; "Šťastní" is also a form of a
        // surname, so this needs the case fix of Dronakurl/harper#67.
        let suggestions = suggestions_for("stastni");
        assert_eq!(
            suggestions.first().map(String::as_str),
            Some("šťastní"),
            "got {suggestions:?}"
        );
        let suggestions = suggestions_for("Dolezity");
        assert_eq!(
            suggestions.first().map(String::as_str),
            Some("Dôležitý"),
            "got {suggestions:?}"
        );
    }

    #[test]
    fn hints_are_loaded() {
        let hints = slovak_suggestion_hints();
        assert!(hints.map.iter().any(|g| g == &["t", "ť"]));
        assert!(!hints.rep.is_empty());
    }

    #[test]
    fn lowercase_typo_keeps_lowercase_suggestions() {
        let suggestions = suggestions_for("nezavisle");
        assert!(
            suggestions.contains(&"nezávisle".to_string()),
            "got {suggestions:?}"
        );
    }

    #[test]
    fn capitalized_typo_gets_capitalized_suggestions() {
        let suggestions = suggestions_for("Nezavisle");
        assert!(
            suggestions.contains(&"Nezávisle".to_string()),
            "got {suggestions:?}"
        );
        assert!(
            suggestions
                .iter()
                .all(|s| s.starts_with(char::is_uppercase)),
            "got {suggestions:?}"
        );
    }

    #[test]
    fn uppercase_typo_gets_uppercase_suggestions() {
        let suggestions = suggestions_for("NEZAVISLE");
        assert!(
            suggestions.contains(&"NEZÁVISLE".to_string()),
            "got {suggestions:?}"
        );
    }

    #[test]
    fn a_word_is_suggested_once_whatever_its_case() {
        let out = merge_case_variants(
            &chars("seí"),
            vec![&chars("Se")[..], &chars("sedí")[..], &chars("se")[..]],
        );
        assert_eq!(strings(out), vec!["se", "sedí"]);
        let out = merge_case_variants(&chars("Seí"), vec![&chars("Se")[..], &chars("se")[..]]);
        assert_eq!(strings(out), vec!["Se"]);
    }

    #[test]
    fn suggestion_with_internal_capital_is_left_alone() {
        let out = match_capitalization(&chars("Ofz"), vec![chars("OFZ"), chars("iPhone")]);
        assert_eq!(strings(out), vec!["OFZ", "iPhone"]);
    }

    #[test]
    fn suggestions_that_become_equal_are_merged() {
        let out = match_capitalization(
            &chars("Bratislva"),
            vec![chars("Bratislava"), chars("bratislava")],
        );
        assert_eq!(strings(out), vec!["Bratislava"]);
    }

    #[test]
    fn single_capital_letter_is_not_treated_as_all_uppercase() {
        let out = match_capitalization(&chars("A"), vec![chars("ab")]);
        assert_eq!(strings(out), vec!["Ab"]);
    }

    #[test]
    fn misspelling_with_suggestions_has_slovak_message() {
        let messages = spell_check_messages("Dohodli sa nezavisle.");
        assert_eq!(messages.len(), 1, "got {messages:?}");
        assert!(
            messages[0].starts_with("Slovo „nezavisle“ môže byť napísané nesprávne. Mysleli ste: "),
            "got {messages:?}"
        );
        assert!(messages[0].contains("nezávisle"), "got {messages:?}");
    }

    #[test]
    fn unknown_word_without_suggestions_has_slovak_message() {
        let messages = spell_check_messages("Dohodli sa qxzqxzqxzqxz.");
        assert_eq!(
            messages,
            vec!["Slovo „qxzqxzqxzqxz“ nie je v slovníku.".to_string()]
        );
    }
}
