//! Slovak for Harper, built as a WebAssembly language plugin.
//!
//! The data come from hunspell-sk through the generator in this repository (`../scripts/`,
//! `../data/`); this crate expands them into a dictionary and checks Slovak text with it.

pub mod language_detection;
pub mod linting;
pub mod messages;
pub mod parsers;
pub mod plugin;
pub mod spell;

#[cfg(target_arch = "wasm32")]
mod wasm_support;
