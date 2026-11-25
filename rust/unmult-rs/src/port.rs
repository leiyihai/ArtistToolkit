//! The Rust port of the `unmult_rgba` pixel kernel in `tools/unmult/core.py`.
//!
//! The Python original works on float32 numpy arrays; every operation here mirrors the same
//! single-precision sequence and order, so the RGBA8 bytes out match the Python kernel byte for
//! byte. `rust-anything diff` replays the recording against this module.

#![forbid(unsafe_code)]

/// 1 级 8bit Alpha,与 Python 侧 `_EPS` 一致。
const EPS: f32 = 1.0 / 255.0;

/// 3×3 去边时 Alpha 视为「半透明边缘」的区间,与 Python 侧一致。
const EDGE_LO: f32 = 0.02;
const EDGE_HI: f32 = 0.98;

#[inline]
fn clamp01(x: f32) -> f32 {
    x.clamp(0.0, 1.0)
}

/// 与 Python `safe_divide` 等价:`np.where(den > eps, num / max(den, eps), 0)`。
#[inline]
fn safe_divide(numerator: f32, denominator: f32) -> f32 {
    if denominator > EPS {
        numerator / denominator.max(EPS)
    } else {
        0.0
    }
}

/// 黑底不透明度 ≈ max(R,G,B)。
#[inline]
fn estimate_alpha_black(r: f32, g: f32, b: f32) -> f32 {
    clamp01(r.max(g).max(b))
}

/// 白底不透明度 ≈ 1 - min(R,G,B)。
#[inline]
fn estimate_alpha_white(r: f32, g: f32, b: f32) -> f32 {
    clamp01(1.0 - r.min(g).min(b))
}

/// float32 颜色 → 8bit:`np.clip(np.round(x * 255), 0, 255).astype(uint8)`,四舍六入五成双。
#[inline]
fn to_u8(x: f32) -> u8 {
    (x * 255.0).round_ties_even().clamp(0.0, 255.0) as u8
}

/// `np.pad(mode="edge")` 的等价:越界坐标夹到边界上。
#[inline]
fn edge_index(v: isize, len: usize) -> usize {
    v.clamp(0, len as isize - 1) as usize
}

/// 半透明边缘去边:边缘像素颜色向 3×3 邻域内 Alpha 更高的像素靠拢。
fn defringe(rgb: &[f32], alpha: &[f32], w: usize, h: usize, strength: f32) -> Vec<f32> {
    let mut out = rgb.to_vec();
    for y in 0..h {
        for x in 0..w {
            let i = y * w + x;
            let a = alpha[i];
            if a <= EDGE_LO || a >= EDGE_HI {
                continue;
            }
            // 累加顺序与 Python 的 (dy, dx) 循环一致,保证 float32 逐位相同。
            let mut acc = [0f32; 3];
            let mut weight = 0f32;
            for dy in -1isize..=1 {
                let sy = edge_index(y as isize + dy, h);
                for dx in -1isize..=1 {
                    let sx = edge_index(x as isize + dx, w);
                    let j = sy * w + sx;
                    let wt = alpha[j];
                    acc[0] += rgb[j * 3] * wt;
                    acc[1] += rgb[j * 3 + 1] * wt;
                    acc[2] += rgb[j * 3 + 2] * wt;
                    weight += wt;
                }
            }
            let denominator = weight.max(1e-6);
            for (c, total) in acc.iter().enumerate() {
                let neighbor = total / denominator;
                let base = rgb[i * 3 + c];
                out[i * 3 + c] = base + strength * (neighbor - base);
            }
        }
    }
    out
}

/// Port of `unmult_rgba` (`tools/unmult/core.py`).
///
/// RGBA8 字节进,RGBA8 字节出:黑底 `C = C_premult / Alpha`,白底
/// `C = (C_premult - (1 - Alpha)) / Alpha`,可选 3×3 去边与 Alpha 重建。
pub fn unmult_rgba(
    data: Vec<u8>,
    width: i64,
    height: i64,
    mode: String,
    defringe_strength: f64,
    rebuild_alpha: bool,
) -> Result<Vec<u8>, String> {
    let black = match mode.as_str() {
        "black" => true,
        "white" => false,
        _ => return Err(format!("ValueError: 未知模式: {mode},可选 black/white")),
    };
    if width <= 0 || height <= 0 {
        return Err("ValueError: 尺寸必须为正整数".to_string());
    }
    if !defringe_strength.is_finite() {
        return Err("ValueError: defringe 必须是有限数值".to_string());
    }
    // Python 的 int 无上限;u128 覆盖 i64::MAX²×4,所以这里不会溢出。
    let expected = (width as u128) * (height as u128) * 4;
    if data.len() as u128 != expected {
        return Err(format!(
            "ValueError: 数据长度应为 {expected}({width}×{height}×4),实际 {}",
            data.len()
        ));
    }

    let w = width as usize;
    let h = height as usize;
    let n = w * h; // 由上面的长度校验保证:data.len() == n * 4
    let mut rgb = vec![0f32; n * 3];
    let mut alpha = vec![0f32; n];
    let mut alpha_min = 1.0f32;
    for (i, px) in data.as_chunks::<4>().0.iter().enumerate() {
        rgb[i * 3] = px[0] as f32 / 255.0;
        rgb[i * 3 + 1] = px[1] as f32 / 255.0;
        rgb[i * 3 + 2] = px[2] as f32 / 255.0;
        let a = px[3] as f32 / 255.0;
        alpha[i] = a;
        if a < alpha_min {
            alpha_min = a;
        }
    }

    // 有 Alpha 通道但完全不透明 → 视为无 Alpha;rebuild_alpha 强制按背景色重估。
    if alpha_min >= 0.999 || rebuild_alpha {
        for i in 0..n {
            let (r, g, b) = (rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]);
            alpha[i] = if black {
                estimate_alpha_black(r, g, b)
            } else {
                estimate_alpha_white(r, g, b)
            };
        }
    }

    // 反预乘:预乘色 → 直通色。
    for (i, &a) in alpha.iter().enumerate() {
        let base = i * 3;
        if black {
            rgb[base] = safe_divide(rgb[base], a);
            rgb[base + 1] = safe_divide(rgb[base + 1], a);
            rgb[base + 2] = safe_divide(rgb[base + 2], a);
        } else {
            let premult_background = 1.0 - a;
            rgb[base] = safe_divide(rgb[base] - premult_background, a);
            rgb[base + 1] = safe_divide(rgb[base + 1] - premult_background, a);
            rgb[base + 2] = safe_divide(rgb[base + 2] - premult_background, a);
        }
    }

    let strength = defringe_strength.clamp(0.0, 1.0) as f32;
    let defringed = if strength > 0.0 {
        Some(defringe(&rgb, &alpha, w, h, strength))
    } else {
        None
    };
    let colors = defringed.as_deref().unwrap_or(&rgb);

    let mut out = vec![0u8; n * 4];
    for (i, &a) in alpha.iter().enumerate() {
        let base = i * 3;
        let o = i * 4;
        out[o] = to_u8(clamp01(colors[base]));
        out[o + 1] = to_u8(clamp01(colors[base + 1]));
        out[o + 2] = to_u8(clamp01(colors[base + 2]));
        out[o + 3] = to_u8(clamp01(a));
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn black_pixel_keeps_its_color_and_loses_its_alpha() {
        // 纯黑背景:不透明度 0,颜色只剩 0。
        let out =
            unmult_rgba(vec![0, 0, 0, 255], 1, 1, "black".into(), 0.0, false).expect("valid input");
        assert_eq!(out, vec![0, 0, 0, 0]);
    }

    #[test]
    fn bright_pixel_on_black_becomes_opaque() {
        let out = unmult_rgba(vec![255, 51, 51, 255], 1, 1, "black".into(), 0.0, false)
            .expect("valid input");
        assert_eq!(out, vec![255, 51, 51, 255]);
    }

    #[test]
    fn white_background_pixel_becomes_transparent() {
        let out = unmult_rgba(vec![255, 255, 255, 255], 1, 1, "white".into(), 0.0, false)
            .expect("valid input");
        assert_eq!(out, vec![0, 0, 0, 0]);
    }

    #[test]
    fn rejects_bad_input_like_the_python_kernel() {
        assert_eq!(
            unmult_rgba(vec![0, 0, 0, 0], 1, 1, "auto".into(), 0.0, false),
            Err("ValueError: 未知模式: auto,可选 black/white".to_string())
        );
        assert_eq!(
            unmult_rgba(vec![0, 0, 0, 0], 0, 1, "black".into(), 0.0, false),
            Err("ValueError: 尺寸必须为正整数".to_string())
        );
        assert_eq!(
            unmult_rgba(vec![], 1, 1, "black".into(), 0.0, false),
            Err("ValueError: 数据长度应为 4(1×1×4),实际 0".to_string())
        );
    }
}
