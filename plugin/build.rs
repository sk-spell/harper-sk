//! Prepares three things the crate includes:
//!
//! - the dictionary data: `../data/trimmed/dictionary.dict` (or `../data/dictionary.dict` with
//!   the `full` feature) and `../data/annotations.json`, the files the generator in this
//!   repository writes from hunspell-sk;
//! - the dictionary pack slot: `pack/slovak.pack` (or `pack/slovak-full.pack`) if it exists and
//!   was baked from exactly these data and this code, else an empty file, in which case the
//!   dictionary is expanded from the word list at first use (see `just bake-pack`);
//! - the Weir rule module (`src/linting/weir_rules/*.weir`, one rule per file, with one test per
//!   rule). Each rule has its message in English (`message`, as Weir expects) and in Slovak
//!   (`messageSk`); the Slovak copy of the rule is written to `OUT_DIR` with `messageSk` as its
//!   message.
//!
//! `SK_DATA_DIR` overrides where the data are read from.

use std::fs;
use std::path::{Path, PathBuf};

fn main() {
    let out_dir = PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
    let stamp = data(&out_dir);
    pack(&out_dir, stamp);
    weir_rules(&out_dir);
}

/// Where the data are, which word list is used, and the stamp a pack must carry to be used.
fn data(out_dir: &Path) -> u64 {
    println!("cargo:rerun-if-env-changed=SK_DATA_DIR");
    let dir = std::env::var_os("SK_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("../data"));
    let full = std::env::var_os("CARGO_FEATURE_FULL").is_some();
    let dict = if full {
        dir.join("dictionary.dict")
    } else {
        dir.join("trimmed/dictionary.dict")
    };
    let annotations = dir.join("annotations.json");

    let mut stamp = Fnv::new();
    stamp.write(if full { b"full" } else { b"trimmed" });
    for path in [&dict, &annotations] {
        println!("cargo:rerun-if-changed={}", path.display());
        let bytes =
            fs::read(path).unwrap_or_else(|e| panic!("cannot read {}: {e}", path.display()));
        stamp.write(&bytes);
    }
    // The pack is the expanded dictionary in the layout of this code; another version of it
    // must not read an old pack.
    for code in ["src/spell/compact_dict.rs", "Cargo.lock"] {
        println!("cargo:rerun-if-changed={code}");
        if let Ok(bytes) = fs::read(code) {
            stamp.write(&bytes);
        }
    }

    let abs = |p: &Path| fs::canonicalize(p).unwrap().display().to_string();
    println!("cargo:rustc-env=SK_DICT_FILE={}", abs(&dict));
    println!("cargo:rustc-env=SK_ANNOTATIONS_FILE={}", abs(&annotations));
    println!("cargo:rustc-env=SK_PACK_STAMP={}", stamp.0);
    println!(
        "cargo:rustc-env=SK_PACK_NAME={}",
        if full {
            "slovak-full.pack"
        } else {
            "slovak.pack"
        }
    );
    let _ = out_dir;
    stamp.0
}

/// Bakes `pack/<name>` in if it carries `stamp`, else an empty slot.
fn pack(out_dir: &Path, stamp: u64) {
    let name = if std::env::var_os("CARGO_FEATURE_FULL").is_some() {
        "slovak-full.pack"
    } else {
        "slovak.pack"
    };
    let source = Path::new("pack").join(name);
    println!("cargo:rerun-if-changed={}", source.display());
    let dest = out_dir.join(name);
    let bytes = fs::read(&source).unwrap_or_default();
    // A pack starts with a magic, its format and its stamp (see `CompactDictionary::to_pack`);
    // one baked from other data is left out rather than rejected at run time.
    let current = bytes.len() >= 16 && bytes[8..16] == stamp.to_le_bytes();
    if !bytes.is_empty() && !current {
        println!(
            "cargo:warning={} is stale (other data or code); run `just bake-pack`",
            source.display()
        );
    }
    fs::write(&dest, if current { &bytes[..] } else { &[] }).unwrap();
    println!("cargo:rustc-env=SK_PACK_FILE={}", dest.display());
}

fn weir_rules(out_dir: &Path) {
    let dir = Path::new("src/linting/weir_rules").canonicalize().unwrap();
    println!("cargo:rerun-if-changed={}", dir.display());

    let mut files: Vec<PathBuf> = fs::read_dir(&dir)
        .unwrap()
        .filter_map(Result::ok)
        .map(|e| e.path())
        .filter(|p| p.is_file() && p.extension().is_some_and(|e| e == "weir"))
        .collect();
    files.sort();

    let names: Vec<String> = files
        .iter()
        .map(|f| {
            println!("cargo:rerun-if-changed={}", f.display());
            f.file_stem().unwrap().to_string_lossy().to_string()
        })
        .collect();

    let sk_dir = out_dir.join("weir_sk");
    fs::create_dir_all(&sk_dir).unwrap();
    for (name, file) in names.iter().zip(&files) {
        let source = fs::read_to_string(file).unwrap();
        fs::write(
            sk_dir.join(format!("{name}.weir")),
            slovak_copy(name, &source),
        )
        .unwrap();
    }

    let source_of = |name: &str| {
        format!("include_str!(concat!(env!(\"SLOVAK_WEIR_RULE_DIR\"), \"/{name}.weir\"))")
    };
    let sk_source_of = |name: &str| {
        format!("include_str!(concat!(env!(\"SLOVAK_WEIR_RULE_SK_DIR\"), \"/{name}.weir\"))")
    };

    let mut code = String::new();
    code.push_str("// Generated by build.rs - do not edit.\n\n");
    code.push_str("use harper_core::linting::LintGroup;\nuse harper_core::weir::WeirLinter;\n\n");
    code.push_str("use crate::messages::MessageLanguage;\n\n");
    code.push_str("/// Every Slovak Weir rule, all enabled, with its messages in `language`.\n");
    code.push_str(
        "pub fn lint_group(language: MessageLanguage) -> LintGroup {\n    let mut group = LintGroup::default();\n\n",
    );
    for name in &names {
        code.push_str(&format!(
            "    let source = match language {{\n        MessageLanguage::Slovak => {},\n        MessageLanguage::English => {},\n    }};\n",
            sk_source_of(name),
            source_of(name)
        ));
        code.push_str("    let linter = WeirLinter::new(source).unwrap();\n");
        code.push_str("    match linter.into_sentence_linter() {\n");
        code.push_str(&format!(
            "        Ok(linter) => group.add_sentence_expr_linter(\"{name}\", linter),\n"
        ));
        code.push_str(&format!(
            "        Err(linter) => group.add_chunk_expr_linter(\n            \"{name}\",\n            linter.into_chunk_linter().unwrap_or_else(|_| unreachable!()),\n        ),\n"
        ));
        code.push_str("    };\n\n");
    }
    code.push_str("    group.set_all_rules_to(Some(true));\n    group\n}\n");

    code.push_str(
        "\n#[cfg(test)]\nmod tests {\n    use harper_core::weir::{TestResult, WeirLinter};\n",
    );
    for name in &names {
        code.push_str(&format!(
            "\n    /// The `test` and `allows` lines in {name}.weir, in both languages.\n    #[test]\n    fn run_tests_for_{}() {{\n        for source in [{}, {}] {{\n            let mut linter = WeirLinter::new(source).unwrap();\n            assert_eq!(Vec::<TestResult>::new(), linter.run_tests());\n        }}\n    }}\n",
            snake(name),
            source_of(name),
            sk_source_of(name)
        ));
    }
    code.push_str("}\n");

    let dest = out_dir.join("slovak_weir_rules.rs");
    fs::write(&dest, code).unwrap();
    println!("cargo:rustc-env=SLOVAK_WEIR_RULE_DIR={}", dir.display());
    println!(
        "cargo:rustc-env=SLOVAK_WEIR_RULE_SK_DIR={}",
        sk_dir.display()
    );
    println!("cargo:rustc-env=SLOVAK_WEIR_RULE_LIST={}", dest.display());
}

/// The rule `source` with its Slovak message (`let messageSk "..."`) in place of the English
/// one (`let message "..."`). Every rule must have both.
fn slovak_copy(name: &str, source: &str) -> String {
    let value_of = |key: &str| {
        let prefix = format!("let {key} ");
        let mut lines = source
            .lines()
            .filter(|l| l.trim_start().starts_with(&prefix));
        let line = lines
            .next()
            .unwrap_or_else(|| panic!("{name}.weir has no `let {key} \"...\"`"));
        assert!(lines.next().is_none(), "{name}.weir sets `{key}` twice");
        line.to_owned()
    };
    let english = value_of("message");
    let slovak = value_of("messageSk");
    let replaced = slovak.replacen("let messageSk ", "let message ", 1);
    source
        .lines()
        .map(|l| if l == english { replaced.as_str() } else { l })
        .collect::<Vec<_>>()
        .join("\n")
        + "\n"
}

fn snake(name: &str) -> String {
    let mut out = String::new();
    for (i, c) in name.chars().enumerate() {
        if c.is_uppercase() {
            if i != 0 {
                out.push('_');
            }
            out.extend(c.to_lowercase());
        } else {
            out.push(c);
        }
    }
    out
}

/// 64-bit FNV-1a, enough to tell data sets apart.
struct Fnv(u64);

impl Fnv {
    fn new() -> Self {
        Self(0xcbf2_9ce4_8422_2325)
    }

    fn write(&mut self, bytes: &[u8]) {
        for b in bytes {
            self.0 ^= u64::from(*b);
            self.0 = self.0.wrapping_mul(0x0000_0100_0000_01b3);
        }
    }
}
