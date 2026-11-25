# Rust migration plan: ArtistToolkit (Python)

1 package, 18 source files (2143 lines), 2 test files, 0 UI files, grouped into 12 units.

| Ready | Caution | Blocked | Keep in source language |
| ---: | ---: | ---: | ---: |
| 7 | 5 | 0 | 0 |

## Start here

Best first ports: safe to port (readiness) and worth porting (loops and string work, tests, size).

| # | Unit | Lines | Priority | Readiness | Tests | Bridge | Main risks |
| ---: | --- | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `tools/unmult/` | 183 | 79 | 73 | 1 | PyO3 | String offsets and slicing (12); Hash iteration order (1); Dynamic typing (13) |
| 2 | `_icon_equiv.py` | 106 | 79 | 72 | 0 | PyO3 | String offsets and slicing (5); Hash iteration order (4); Division and modulo (4) |
| 3 | `check_pack.py` | 43 | 77 | 100 | 0 | PyO3 | Exceptions (1) |
| 4 | `tools/img2box/` | 213 | 68 | 73 | 0 | PyO3 | String offsets and slicing (1); Dynamic typing (8); Division and modulo (7) |
| 5 | `tools/icon_export/legacy/` | 289 | 67 | 69 | 0 | PyO3 | String offsets and slicing (4); Division and modulo (10); Dynamic typing (2) |
| 6 | `main.py` | 77 | 64 | 90 | 0 | PyO3 | Dynamic typing (5); Class inheritance (1); Exceptions (2) |

### `tools/unmult/`

183 lines in 1 file, wave 0, priority 79, readiness 73, bridge **PyO3**.

- Leaf: imports no other unit.
- 1 test file imports it directly.
- String offsets and slicing x12: `tools/unmult/core.py:64`, `tools/unmult/core.py:65`, `tools/unmult/core.py:106`
- Hash iteration order x1: `tools/unmult/core.py:17`
- Dynamic typing x13: `tools/unmult/core.py:22`, `tools/unmult/core.py:26`, `tools/unmult/core.py:32`
- Exceptions x9: `tools/unmult/core.py:96`, `tools/unmult/core.py:98`, `tools/unmult/core.py:100`
- Number semantics x1: `tools/unmult/core.py:68`

### `_icon_equiv.py`

106 lines in 1 file, wave 0, priority 79, readiness 72, bridge **PyO3**.

- Leaf: imports no other unit.
- String offsets and slicing x5: `_icon_equiv.py:52`, `_icon_equiv.py:98`, `_icon_equiv.py:99`
- Hash iteration order x4: `_icon_equiv.py:121`, `_icon_equiv.py:122`
- Division and modulo x4: `_icon_equiv.py:39`, `_icon_equiv.py:61`
- Dynamic typing x1: `_icon_equiv.py:15`
- Number semantics x2: `_icon_equiv.py:121`, `_icon_equiv.py:122`
- Exceptions x1: `_icon_equiv.py:129`

### `check_pack.py`

43 lines in 1 file, wave 0, priority 77, readiness 100, bridge **PyO3**.

- Leaf: imports no other unit.
- Exceptions x1: `check_pack.py:22`

### `tools/img2box/`

213 lines in 1 file, wave 0, priority 68, readiness 73, bridge **PyO3**.

- Leaf: imports no other unit.
- String offsets and slicing x1: `tools/img2box/core.py:176`
- Dynamic typing x8: `tools/img2box/core.py:44`, `tools/img2box/core.py:58`, `tools/img2box/core.py:67`
- Division and modulo x7: `tools/img2box/core.py:72`, `tools/img2box/core.py:75`, `tools/img2box/core.py:236`
- Concurrency x2: `tools/img2box/core.py:218`, `tools/img2box/core.py:222`
- Class inheritance x1: `tools/img2box/core.py:151`
- Exceptions x9: `tools/img2box/core.py:46`, `tools/img2box/core.py:87`, `tools/img2box/core.py:90`

### `tools/icon_export/legacy/`

289 lines in 5 files, wave 0, priority 67, readiness 69, bridge **PyO3**.

- 1 PyPI dependencies not in the crate table: check them by hand.
- Leaf: imports no other unit.
- String offsets and slicing x4: `tools/icon_export/legacy/run.py:38`, `tools/icon_export/legacy/run.py:52`, `tools/icon_export/legacy/run.py:71`
- Division and modulo x10: `tools/icon_export/legacy/crop_to_circle.py:48`, `tools/icon_export/legacy/crop_to_circle.py:49`, `tools/icon_export/legacy/crop_to_rounded_square.py:55`
- Dynamic typing x2: `tools/icon_export/legacy/run.py:20`, `tools/icon_export/legacy/run.py:47`
- Integer width and overflow x1: `tools/icon_export/legacy/normalize_icons.py:54`
- Exceptions x5: `tools/icon_export/legacy/crop_to_circle.py:36`, `tools/icon_export/legacy/crop_to_rounded_square.py:42`, `tools/icon_export/legacy/crop_to_square.py:39`

## Order by package

Packages come after the workspace packages they use. Inside a package, port by wave: a unit's imports are in earlier waves.

### 1. root (`.`, portable, 2 test files)

| Wave | Unit | Status | Lines | Readiness | Bridge | Main risks |
| ---: | --- | --- | ---: | ---: | --- | --- |
| 0 | `check_pack.py` | ready | 43 | 100 | PyO3 | Exceptions (1) |
| 0 | `tools/` | ready | 0 | 100 | PyO3 | - |
| 0 | `tools/img2box/assets/` | caution | 145 | 89 | PyO3 | String offsets and slicing (2); Exceptions (1) |
| 0 | `tools/image_resize/` | caution | 130 | 87 | PyO3 | Dynamic typing (4); Division and modulo (2) |
| 0 | `tools/ai_matting/` | caution | 111 | 81 | PyO3 | String offsets and slicing (1); Division and modulo (4) |
| 0 | `tools/img2box/` | ready | 213 | 73 | PyO3 | String offsets and slicing (1); Dynamic typing (8) |
| 0 | `tools/unmult/` | ready | 183 | 73 | PyO3 | String offsets and slicing (12); Hash iteration order (1) |
| 0 | `_icon_equiv.py` | ready | 106 | 72 | PyO3 | String offsets and slicing (5); Hash iteration order (4) |
| 0 | `tools/icon_export/legacy/` | ready | 289 | 69 | PyO3 | String offsets and slicing (4); Division and modulo (10) |
| 0 | `tools/icon_export/` | caution | 707 | 35 | PyO3 | String offsets and slicing (9); Hash iteration order (1) |
| 1 | `main.py` | ready | 77 | 90 | PyO3 | Dynamic typing (5); Class inheritance (1) |
| 1 | `backend.py` | caution | 139 | 81 | PyO3 | Hash iteration order (1); Concurrency (6) |

## PyPI dependencies

| Package | Units | Rust | Fit | Note |
| --- | ---: | --- | --- | --- |
| `rembg` | 4 | ? | unknown |  |
| `tkinterdnd2` | 2 | ? | unknown |  |
| `bpy` | 1 | ? | unknown |  |
| `pil` | 7 | image | partial |  |
| `numpy` | 6 | ndarray | partial | Broadcasting and dtype rules differ; check numerics. |
| `scipy` | 3 | ndarray, statrs | partial |  |

## Risk guide

- **String offsets and slicing** (High): JS indexes strings in UTF-16 code units, Rust in UTF-8 bytes. Offsets that cross the boundary must be converted, or non-ASCII text gets wrong ranges silently.
- **Dynamic typing** (Medium): Values whose shape is checked at runtime need an explicit Rust enum or `serde_json::Value`.
- **Exceptions** (Low): Thrown errors become `Result`. Errors crossing the bridge must map back to the same JS error shape.
- **Class inheritance** (Medium): Class hierarchies become traits plus composition; `instanceof` checks become enums.
- **Number semantics** (Low): JS numbers are f64; bitwise ops truncate to i32; parseInt is lenient. Pick Rust integer types deliberately. Printing differs: `${n}` gives `1e+21`, `1e-7` and `0` for -0 where Rust's `{}` does not, so use `js::number_to_string`. `Math.round` rounds halves up (-2.5 gives -2), Rust's `round` away from zero: use `js::math_round`. `toFixed` rounds exact halves up ((2.5).toFixed(0) is "3"), Rust's `{:.0}` to even.
- **Integer width and overflow** (Medium): Python ints never overflow; C, Go and Java ints wrap or are undefined on overflow. Pick i64, i128 or a bignum crate deliberately, and use wrapping_* where the source wraps.
- **Division and modulo** (Medium): Python `//` and `%` floor toward negative infinity; Rust `/` and `%` truncate: use `div_euclid`/`rem_euclid` or explicit floor math. C division by zero is undefined.
- **Hash iteration order** (High): Set and map iteration order comes from the source language's hash function. A port cannot reproduce it: sort before output, or make the order part of the contract.
- **Concurrency** (Medium): Threads, goroutines and locks need a design in Rust (channels, Send/Sync), not a line-by-line translation; keep concurrency in the caller where possible.
