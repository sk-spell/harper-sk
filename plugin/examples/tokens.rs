//! Print the tokens the Slovak parser makes of a text.
use harper_core::parsers::Parser;
fn main() {
    for t in std::env::args().skip(1) {
        let c: Vec<char> = t.chars().collect();
        for tok in harper_sk::parsers::PlainSlovak.parse(&c) {
            let s: String = c[tok.span.start..tok.span.end].iter().collect();
            println!("{t:?}: {s:?} {:?}", std::mem::discriminant(&tok.kind));
        }
    }
}
