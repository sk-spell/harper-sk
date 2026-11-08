//! The Slovak dictionary and suggestion hints.

pub mod compact_dict;

use std::sync::{Arc, LazyLock};

use harper_core::spell::SuggestionHints;
use harper_core::spell::rune::{AttributeList, parse_word_list};

use compact_dict::{CompactDictionary, expand_in_blocks};

/// The word list (`dictionary.dict`) the plugin is built with.
pub const WORD_LIST: &str = include_str!(env!("SK_DICT_FILE"));
/// The affixes, properties and suggestion hints (`annotations.json`).
pub const ANNOTATIONS: &str = include_str!(env!("SK_ANNOTATIONS_FILE"));
/// The expanded dictionary baked in by `build.rs`, or empty.
const PACK: &[u8] = include_bytes!(env!("SK_PACK_FILE"));

/// What a pack must have been built from to be used: the data and the code that lays it out
/// (computed by `build.rs`).
pub fn pack_stamp() -> u64 {
    env!("SK_PACK_STAMP").parse().unwrap()
}

/// Expand the word list through the annotations.
pub fn expand_dictionary() -> CompactDictionary {
    let attributes =
        AttributeList::parse(ANNOTATIONS).expect("Failed to parse the Slovak annotations");
    let words = parse_word_list(WORD_LIST).expect("Failed to parse the Slovak word list");
    expand_in_blocks(&attributes, &words)
}

/// The expanded dictionary, written as a pack (see `just bake-pack`).
pub fn bake_pack() -> Vec<u8> {
    expand_dictionary().to_pack(pack_stamp())
}

static DICTIONARY: LazyLock<Arc<CompactDictionary>> = LazyLock::new(|| {
    let dictionary = if PACK.is_empty() {
        None
    } else {
        CompactDictionary::from_pack(PACK, pack_stamp()).ok()
    };
    Arc::new(dictionary.unwrap_or_else(expand_dictionary))
});

/// The Slovak dictionary, built once.
pub fn slovak_dictionary() -> Arc<CompactDictionary> {
    Arc::clone(&DICTIONARY)
}

/// Whether the dictionary comes from a baked pack rather than from expanding the word list.
pub fn has_pack() -> bool {
    !PACK.is_empty()
}

static HINTS: LazyLock<SuggestionHints> = LazyLock::new(|| {
    SuggestionHints::from_annotations_json(ANNOTATIONS)
        .unwrap_or_else(|e| panic!("Failed to read the Slovak suggestion hints: {e}"))
});

/// The suggestion hints (REP, MAP, KEY, TRY) imported from `sk_SK.aff` into the `suggestions`
/// section of `annotations.json`.
pub fn slovak_suggestion_hints() -> &'static SuggestionHints {
    &HINTS
}
