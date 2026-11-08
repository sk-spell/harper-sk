//! Writes the expanded dictionary to `pack/slovak.pack` (or `pack/slovak-full.pack` with the
//! `full` feature), which `build.rs` then bakes into the plugin. Run it via `just bake-pack`.

fn main() {
    let out = std::env::args()
        .nth(1)
        .unwrap_or_else(|| format!("pack/{}", env!("SK_PACK_NAME")));
    let pack = harper_sk::spell::bake_pack();
    if let Some(dir) = std::path::Path::new(&out).parent() {
        std::fs::create_dir_all(dir).unwrap();
    }
    std::fs::write(&out, &pack).unwrap();
    eprintln!("wrote {out}: {} bytes", pack.len());
}
