## `unmult-rs` in Rust

![unmult-rs report card](card.svg)

| | |
| --- | --- |
| Unit | `tools/unmult/` (Python) |
| Recorded cases matched | 291 / 291 |
| Speedup, call included | 22x (geometric mean) |
| Fallback to the original | 0.0% (0 of 291 cases) |
| Switched on | on |

| Function | Cases | Original per call | Rust per call | Speedup |
| --- | ---: | ---: | ---: | ---: |
| `unmult_rgba` | 291 | 51.7 µs | 2.3 µs | 22x |

Measured with `rust-anything report` on x86_64, 16 cores, Windows: `diff` replays every recorded case, `bench` times them on both sides as callers call them. Reproduce: `rust-anything diff` and `rust-anything bench` in the crate folder.
