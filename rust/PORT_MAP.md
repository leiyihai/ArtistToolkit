# Port map: ArtistToolkit

2 of 12 units have a Rust port; no original changed since it was recorded.

## Ports

| Unit | Crate | In Rust | Kept in the original | Cases | Last diff | Original |
| --- | --- | --- | --- | ---: | ---: | --- |
| `tools/icon_export/` | `rust/icon-export-rs` | `segment_component_boxes` | `process_batch`, `ImageList`, `ExportPage` | 156 | 156/156 | unchanged |
| `tools/unmult/` | `rust/unmult-rs` | `unmult_rgba` | `process_batch` | 291 | 291/291 | unchanged |

## Not ported yet

In the order `analyze` suggests.

| Unit | Status | Lines | Exports | Readiness |
| --- | --- | ---: | ---: | ---: |
| `_icon_equiv.py` | ready | 106 | 8 | 72 |
| `check_pack.py` | ready | 43 | 2 | 100 |
| `tools/img2box/` | ready | 213 | 7 | 73 |
| `tools/icon_export/legacy/` | ready | 289 | 6 | 69 |
| `main.py` | ready | 77 | 3 | 90 |
| `tools/image_resize/` | caution | 130 | 1 | 87 |
| `tools/img2box/assets/` | caution | 145 | 1 | 89 |
| `backend.py` | caution | 139 | 3 | 81 |
| `tools/ai_matting/` | caution | 111 | 1 | 81 |
| `tools/` | ready | 0 | 0 | 100 |

Regenerate with `rust-anything map --write`. Commit this file: when the original changes upstream, the next map marks every port whose recording it outdated.
