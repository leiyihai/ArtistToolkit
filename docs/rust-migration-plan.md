# Rust migration plan: ArtistToolkit (Python)

1 package, 10 source files (1565 lines), 2 test files, 0 UI files, grouped into 9 units.

| Ready | Caution | Blocked | Keep in source language |
| ---: | ---: | ---: | ---: |
| 3 | 4 | 2 | 0 |

## Start here

Best first ports: safe to port (readiness) and worth porting (loops and string work, tests, size).

| # | Unit | Lines | Priority | Readiness | Tests | Bridge | Main risks |
| ---: | --- | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `ui/scripts/` | 77 | 73 | 96 | 0 | PyO3 | Dynamic typing (4); Exceptions (2) |
| 2 | `tools/img2box/` | 213 | 68 | 73 | 0 | PyO3 | String offsets and slicing (1); Dynamic typing (8); Division and modulo (7) |

### `ui/scripts/`

77 lines in 1 file, wave 0, priority 73, readiness 96, bridge **PyO3**.

- Leaf: imports no other unit.
- Dynamic typing x4: `ui/scripts/capture_reference.py:42`, `ui/scripts/capture_reference.py:46`, `ui/scripts/capture_reference.py:57`
- Exceptions x2: `ui/scripts/capture_reference.py:38`, `ui/scripts/capture_reference.py:54`

### `tools/img2box/`

213 lines in 1 file, wave 0, priority 68, readiness 73, bridge **PyO3**.

- Leaf: imports no other unit.
- String offsets and slicing x1: `tools/img2box/core.py:176`
- Dynamic typing x8: `tools/img2box/core.py:44`, `tools/img2box/core.py:58`, `tools/img2box/core.py:67`
- Division and modulo x7: `tools/img2box/core.py:72`, `tools/img2box/core.py:75`, `tools/img2box/core.py:236`
- Concurrency x2: `tools/img2box/core.py:218`, `tools/img2box/core.py:222`
- Class inheritance x1: `tools/img2box/core.py:151`
- Exceptions x9: `tools/img2box/core.py:46`, `tools/img2box/core.py:87`, `tools/img2box/core.py:90`

## Order by package

Packages come after the workspace packages they use. Inside a package, port by wave: a unit's imports are in earlier waves.

### 1. root (`.`, portable, 2 test files)

| Wave | Unit | Status | Lines | Readiness | Bridge | Main risks |
| ---: | --- | --- | ---: | ---: | --- | --- |
| 0 | `tools/` | ready | 0 | 100 | PyO3 | - |
| 0 | `ui/scripts/` | ready | 77 | 96 | PyO3 | Dynamic typing (4); Exceptions (2) |
| 0 | `tools/img2box/assets/` | caution | 145 | 89 | PyO3 | String offsets and slicing (2); Exceptions (1) |
| 0 | `tools/image_resize/` | caution | 130 | 87 | PyO3 | Dynamic typing (4); Division and modulo (2) |
| 0 | `tools/ai_matting/` | caution | 135 | 81 | PyO3 | String offsets and slicing (1); Division and modulo (4) |
| 0 | `tools/img2box/` | ready | 213 | 73 | PyO3 | String offsets and slicing (1); Dynamic typing (8) |
| 0 | `tools/unmult/` | blocked | 201 | 66 | PyO3 | String offsets and slicing (12); Dynamic code (eval, new Function, computed import) (1) |
| 0 | `tools/icon_export/` | blocked | 520 | 47 | PyO3 | String offsets and slicing (8); Dynamic code (eval, new Function, computed import) (1) |
| 1 | `backend.py` | caution | 144 | 81 | PyO3 | Hash iteration order (1); Concurrency (6) |

## PyPI dependencies

| Package | Units | Rust | Fit | Note |
| --- | ---: | --- | --- | --- |
| `rembg` | 3 | ? | unknown |  |
| `bpy` | 1 | ? | unknown |  |
| `pil` | 5 | image | partial |  |
| `numpy` | 4 | ndarray | partial | Broadcasting and dtype rules differ; check numerics. |
| `scipy` | 2 | ndarray, statrs | partial |  |
| `websocket` | 1 | tokio-tungstenite | good |  |

## Blocked

- `tools/icon_export/`: Uses dynamic code (eval, new Function or computed imports).
- `tools/unmult/`: Uses dynamic code (eval, new Function or computed imports).

## Risk guide

- **String offsets and slicing** (High): JS indexes strings in UTF-16 code units, Rust in UTF-8 bytes. Offsets that cross the boundary must be converted, or non-ASCII text gets wrong ranges silently.
- **Dynamic code (eval, new Function, computed import)** (High): eval, new Function and computed imports have no Rust equivalent. Keep this part in JS or replace it with an explicit registry.
- **Dynamic typing** (Medium): Values whose shape is checked at runtime need an explicit Rust enum or `serde_json::Value`.
- **Exceptions** (Low): Thrown errors become `Result`. Errors crossing the bridge must map back to the same JS error shape.
- **Class inheritance** (Medium): Class hierarchies become traits plus composition; `instanceof` checks become enums.
- **Reflection and prototypes** (Medium): Proxy, Reflect, Symbol and prototype tricks need a redesign, not a translation.
- **Number semantics** (Low): JS numbers are f64; bitwise ops truncate to i32; parseInt is lenient. Pick Rust integer types deliberately. Printing differs: `${n}` gives `1e+21`, `1e-7` and `0` for -0 where Rust's `{}` does not, so use `js::number_to_string`. `Math.round` rounds halves up (-2.5 gives -2), Rust's `round` away from zero: use `js::math_round`. `toFixed` rounds exact halves up ((2.5).toFixed(0) is "3"), Rust's `{:.0}` to even.
- **Integer width and overflow** (Medium): Python ints never overflow; C, Go and Java ints wrap or are undefined on overflow. Pick i64, i128 or a bignum crate deliberately, and use wrapping_* where the source wraps.
- **Division and modulo** (Medium): Python `//` and `%` floor toward negative infinity; Rust `/` and `%` truncate: use `div_euclid`/`rem_euclid` or explicit floor math. C division by zero is undefined.
- **Hash iteration order** (High): Set and map iteration order comes from the source language's hash function. A port cannot reproduce it: sort before output, or make the order part of the contract.
- **Concurrency** (Medium): Threads, goroutines and locks need a design in Rust (channels, Send/Sync), not a line-by-line translation; keep concurrency in the caller where possible.
