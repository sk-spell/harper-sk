//! Slovak text parsers.

use harper_core::lexing::{FoundToken, lex_english_token, lex_with, lex_word};
use harper_core::parsers::Parser;
use harper_core::{Token, TokenKind};

/// A parser that lexes as many tokens as possible, until the end of input.
///
/// Slovak words, numbers, URLs and e-mail addresses split the same way as English ones, so the
/// English lexer is reused, with one exception (see [`lex_slovak_token`]).
#[derive(Clone, Copy)]
pub struct PlainSlovak;

impl Parser for PlainSlovak {
    fn parse(&self, source: &[char]) -> Vec<Token> {
        lex_with(source, lex_slovak_token)
    }

    /// Not English, so [`Document`](harper_core::Document) skips the Brill tagger and the
    /// neural chunker, which are English-only models.
    fn is_english(&self) -> bool {
        false
    }
}

/// The English lexer, except that a word never ends in the middle of letters.
///
/// The English lexer reads two ASCII characters ending in `s` followed by anything but an ASCII
/// letter or digit as a word of its own (for "1s" and "Bs", Automattic/harper#774). Slovak "usídli"
/// then becomes "us" and "ídli", and the second half is flagged as a misspelling.
pub fn lex_slovak_token(source: &[char]) -> FoundToken {
    let found = lex_english_token(source);
    let cut_inside_a_word = matches!(found.token, TokenKind::Word(_))
        && source
            .get(found.next_index)
            .is_some_and(|c| c.is_alphabetic());
    if cut_inside_a_word {
        lex_word(source).unwrap_or(found)
    } else {
        found
    }
}

#[cfg(test)]
mod tests {
    use harper_core::parsers::Parser;

    use super::PlainSlovak;

    fn words(text: &str) -> Vec<String> {
        let chars: Vec<char> = text.chars().collect();
        PlainSlovak
            .parse(&chars)
            .into_iter()
            .filter(|t| t.kind.is_word())
            .map(|t| chars[t.span.start..t.span.end].iter().collect())
            .collect()
    }

    #[test]
    fn a_word_with_s_and_a_diacritic_stays_whole() {
        assert_eq!(
            words("usídli usúdil osírotieť isú"),
            ["usídli", "usúdil", "osírotieť", "isú"]
        );
    }

    #[test]
    fn plural_digits_still_lex_as_before() {
        assert_eq!(words("1s and Bs, as is"), ["1s", "and", "Bs", "as", "is"]);
    }
}
