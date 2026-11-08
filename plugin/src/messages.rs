//! The language the plugin's messages are written in.
//!
//! A message belongs to the interface around it: someone who reads Slovak text in an English
//! browser sees an English title and English buttons, so the sentence between them should be
//! English too. The plugin keeps every message in Slovak and English. Until the host says which
//! language its interface uses, the messages follow the text and stay Slovak.

/// The language of the messages the rules write.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum MessageLanguage {
    /// The language of the text, used when the host does not name one.
    #[default]
    Slovak,
    English,
}

impl MessageLanguage {
    /// The message language for an interface language given as a BCP 47 tag (`sk`, `sk-SK`,
    /// `en-GB`, `de`). Slovak for a Slovak interface; English for any other, because English is
    /// what the rest of a non-Slovak interface around the message is in. `None` for an empty or
    /// malformed tag, which leaves the messages as they are.
    pub fn for_interface(tag: &str) -> Option<Self> {
        let primary = tag.split(['-', '_']).next()?.trim();
        if primary.is_empty() || !primary.chars().all(|c| c.is_ascii_alphabetic()) {
            return None;
        }
        Some(if primary.eq_ignore_ascii_case("sk") {
            Self::Slovak
        } else {
            Self::English
        })
    }

    /// `slovak` or `english`, whichever is in this language.
    pub fn pick<'a>(self, slovak: &'a str, english: &'a str) -> &'a str {
        match self {
            Self::Slovak => slovak,
            Self::English => english,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::MessageLanguage;

    #[test]
    fn a_slovak_interface_gets_slovak_messages() {
        for tag in ["sk", "sk-SK", "SK", "sk_SK"] {
            assert_eq!(
                MessageLanguage::for_interface(tag),
                Some(MessageLanguage::Slovak),
                "{tag}"
            );
        }
    }

    #[test]
    fn any_other_interface_gets_english_messages() {
        for tag in ["en", "en-GB", "en_UK", "de-DE", "cs"] {
            assert_eq!(
                MessageLanguage::for_interface(tag),
                Some(MessageLanguage::English),
                "{tag}"
            );
        }
    }

    #[test]
    fn a_tag_that_is_not_one_changes_nothing() {
        for tag in ["", "-", "1x", " "] {
            assert_eq!(MessageLanguage::for_interface(tag), None, "{tag:?}");
        }
    }

    #[test]
    fn without_a_tag_the_messages_are_slovak() {
        assert_eq!(MessageLanguage::default(), MessageLanguage::Slovak);
    }
}
