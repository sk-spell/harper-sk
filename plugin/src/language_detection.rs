//! Is a text Slovak?
//!
//! Built on signals that need no dictionary, so that a host can ask before the plugin loads:
//! - letters only Slovak uses among its neighbours (ľ, ĺ, ŕ, ô) and words with ä together with
//!   another Slovak letter ("päť", "späť"): very high confidence;
//! - letters Slovak shares with Czech (č, š, ž, ť, ď, ň, á, é, í, ó, ú, ý): high confidence, unless
//!   letters only Czech (ě, ř, ů) or only Polish (ą, ę, ł, ś, ź, ż, ń) outnumber the Slovak ones;
//! - how many words are common Slovak function words, and how many are English ones.
//!
//! Harper picks the plugin that is surest. German answers 0.95 when enough words have ä, ö, ü
//! or ß, so the strongest Slovak signal answers more than that; a word like "mäso", with ä and
//! nothing else, counts for neither.

use harper_core::parsers::Parser;
use harper_core::{Token, TokenKind};

use crate::parsers::PlainSlovak;

/// Words so common in Slovak that a text with many of them is Slovak.
const SLOVAK_WORDS: &[&str] = &[
    "ja", "ty", "on", "ona", "ono", "my", "vy", "oni", "ony", "mňa", "teba", "ho", "ju", "nás",
    "vás", "som", "si", "je", "sme", "ste", "sú", "mám", "máš", "má", "máme", "máte", "majú",
    "nie", "áno", "aj", "ale", "a", "i", "alebo", "v", "z", "do", "na", "pri", "po", "pre", "o",
    "k", "od", "za", "pod", "nad", "medzi", "bez", "cez", "sa", "to", "ako", "že", "čo", "ktorý",
    "ktorá", "ktoré", "tak", "už", "ešte", "len", "veľmi",
];

/// English function words that are not also Slovak words.
const ENGLISH_WORDS: &[&str] = &[
    "the", "and", "of", "is", "it", "that", "for", "with", "as", "are", "be", "this", "by", "from",
    "or", "have", "not", "but", "they", "you", "we", "he", "she", "his", "her", "their", "which",
    "at", "were", "been", "has", "had", "would", "there", "what", "when", "your", "can", "will",
    "all", "if", "about", "into", "than", "then", "its", "who", "how",
];

/// Letters Slovak has and its neighbours (Czech, Polish, German, Hungarian) do not.
const SLOVAK_ONLY: &[char] = &['ľ', 'ĺ', 'ŕ', 'ô'];
/// Letters Slovak shares with Czech.
const SHARED_WITH_CZECH: &[char] = &['č', 'š', 'ž', 'ť', 'ď', 'ň', 'á', 'é', 'í', 'ó', 'ú', 'ý'];
/// Letters of Czech or Polish that Slovak does not use.
const OTHER_SLAVIC: &[char] = &['ě', 'ř', 'ů', 'ą', 'ę', 'ł', 'ś', 'ź', 'ż', 'ń'];

/// How sure we are that `text` is Slovak, from 0 to 1, or `None` if there is nothing to go on
/// (too short, or clearly something else).
pub fn slovak_confidence(text: &str) -> Option<f32> {
    let counts = Counts::of_text(text)?;
    counts.by_letters().unwrap_or_else(|| {
        let english = counts.ratio(counts.english);
        counts.by_words(english >= 0.25, english < 0.10)
    })
}

/// [`slovak_confidence`] when the host says how much of `text` is English: `english_ratio` is
/// the share of its words in Harper's English dictionary.
pub fn slovak_confidence_given_english(text: &str, english_ratio: f32) -> Option<f32> {
    let counts = Counts::of_text(text)?;
    counts
        .by_letters()
        .unwrap_or_else(|| counts.by_words(english_ratio >= 0.65, english_ratio < 0.4))
}

/// What the confidence is computed from.
struct Counts {
    total: usize,
    slovak_only: usize,
    shared: usize,
    other_slavic: usize,
    slovak: usize,
    english: usize,
}

impl Counts {
    fn of_text(text: &str) -> Option<Self> {
        let chars: Vec<char> = text.chars().collect();
        Self::of(&PlainSlovak.parse(&chars), &chars)
    }

    /// `None` when there are too few words to judge reliably.
    fn of(tokens: &[Token], source: &[char]) -> Option<Self> {
        let mut counts = Self {
            total: 0,
            slovak_only: 0,
            shared: 0,
            other_slavic: 0,
            slovak: 0,
            english: 0,
        };
        for token in tokens {
            if !matches!(token.kind, TokenKind::Word(_)) {
                continue;
            }
            counts.total += 1;
            let word: String = token
                .get_ch(source)
                .iter()
                .collect::<String>()
                .to_lowercase();
            let shared = word.contains(SHARED_WITH_CZECH);
            if word.contains(SLOVAK_ONLY) || (word.contains('ä') && shared) {
                counts.slovak_only += 1;
            } else if shared {
                counts.shared += 1;
            }
            if word.contains(OTHER_SLAVIC) {
                counts.other_slavic += 1;
            }
            if SLOVAK_WORDS.contains(&word.as_str()) {
                counts.slovak += 1;
            }
            if ENGLISH_WORDS.contains(&word.as_str()) {
                counts.english += 1;
            }
        }
        (counts.total >= 5).then_some(counts)
    }

    fn ratio(&self, n: usize) -> f32 {
        n as f32 / self.total as f32
    }

    /// The answer from the letters alone, if they settle it: `Some(None)` when they show
    /// Czech or Polish, `None` when they say nothing.
    fn by_letters(&self) -> Option<Option<f32>> {
        if self.other_slavic > 0 && self.other_slavic >= self.slovak_only + self.shared / 2 {
            return Some(None);
        }
        if self.ratio(self.slovak_only) >= 0.01 {
            return Some(Some(0.97));
        }
        if self.ratio(self.shared) >= 0.05 {
            return Some(Some(0.9));
        }
        None
    }

    /// The answer from common words: `english_dominant` rules Slovak out, and with
    /// `english_low` fewer Slovak words are enough.
    fn by_words(&self, english_dominant: bool, english_low: bool) -> Option<f32> {
        if english_dominant {
            return None;
        }
        let slovak = self.ratio(self.slovak);
        if slovak >= 0.20 {
            return Some(0.85);
        }
        if english_low && slovak >= 0.08 {
            return Some(0.6);
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::{slovak_confidence, slovak_confidence_given_english};

    fn is_slovak(text: &str) -> bool {
        slovak_confidence(text).is_some()
    }

    #[test]
    fn detects_slovak_special_chars() {
        assert!(is_slovak("Ja som Šťastný. Čo robíš? Žijeme v Bratislave."));
    }

    #[test]
    fn detects_common_slovak_words() {
        assert!(is_slovak(
            "Ja som v dome. Ty si v škole. On je v práci. My sme šťastní."
        ));
    }

    #[test]
    fn detects_slovak_without_diacritics() {
        assert!(is_slovak(
            "ja som v dome a ty si v skole a on je v praci a my sme tu"
        ));
    }

    #[test]
    fn detects_mixed_slovak_english() {
        assert!(is_slovak("Ja som happy v dome. Ty si tired v škole."));
    }

    #[test]
    fn rejects_english() {
        assert!(!is_slovak(
            "I am happy in the house. You are tired at school. He is at work."
        ));
        assert_eq!(
            slovak_confidence_given_english(
                "I am happy in the house. You are tired at school. He is at work.",
                0.9
            ),
            None
        );
    }

    #[test]
    fn rejects_short_text() {
        assert!(!is_slovak("Ja som"));
    }

    #[test]
    fn rejects_german() {
        assert!(!is_slovak(
            "Die Katze schläft im Garten, und wir gehen später nach Hause."
        ));
    }

    #[test]
    fn rejects_czech_and_polish() {
        assert!(!is_slovak(
            "Dobrý den, já jsem tady. Řekl mi, že ten dům je hezčí než můj."
        ));
        assert!(!is_slovak(
            "Dzień dobry, jestem tutaj. Powiedział mi, że ten dom jest ładniejszy."
        ));
    }

    #[test]
    fn slovak_with_umlaut_is_surer_than_german_would_be() {
        // German answers 0.95 for umlauts; "späť" and "päť" must not lose the text to German.
        let text = "Vďaka tomu sa vrátil späť. Zrejme konečne prišlo päť rokov. Sme šťastní.";
        assert!(slovak_confidence(text).unwrap() > 0.95);
    }

    #[test]
    fn detects_longer_slovak_text() {
        assert!(is_slovak(
            "Ja som student na univerzite v Bratislave. \
             Ty si učiteľ a robíš v škole. \
             On je programátor a pracuje v kancelárii. \
             My sme šťastní a spokojní s našim životom."
        ));
    }
}
