//! Look words up in the plugin's dictionary: whether each is a word, and its spellings.
use harper_core::spell::Dictionary;
fn main() {
    let d = harper_sk::spell::slovak_dictionary();
    for w in std::env::args().skip(1) {
        let c: Vec<char> = w.chars().collect();
        let caps: Vec<String> = d
            .get_correct_capitalizations_of(&c)
            .map(|x| x.iter().collect())
            .collect();
        println!(
            "{w}: contains {} exact {} spellings {caps:?}",
            d.contains_word(&c),
            d.contains_exact_word(&c)
        );
    }
}
