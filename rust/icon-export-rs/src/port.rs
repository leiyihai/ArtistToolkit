//! The Rust port of `segment_component_boxes` in `tools/icon_export/core.py`.
//!
//! Python 用 `scipy.ndimage.label` 标连通域,再对每个连通域做一次全图 `np.where` 求外接框;
//! 这里一趟扫描 + 显式栈的洪水填充同时得到面积与外接框,标签顺序无关(下游会排序合并),
//! 所以与 scipy 的标号顺序不同也不影响结果。

#![forbid(unsafe_code)]

/// 低于该像素数的连通域视为噪声(与 Python 侧 `MIN_ICON_PIXELS` 一致)。
const MIN_ICON_PIXELS: u64 = 500;
/// Alpha 低于该值视为背景(与 Python 侧 `alpha > 10` 一致)。
const ALPHA_THRESHOLD: u8 = 10;

/// 一个连通域:面积、外接框。
struct Component {
    size: u64,
    x1: usize,
    y1: usize,
    x2: usize,
    y2: usize,
}

/// Port of `segment_component_boxes` (`tools/icon_export/core.py`).
///
/// RGBA8 字节 → 前景(Alpha>10)连通域外接框,扁平返回 `[x1,y1,x2,y2,…]`,
/// 按 `(y1,x1,y2,x2)` 排序,已滤掉小于 500 px 或不足最大块 2% 的碎块。
pub fn segment_component_boxes(data: Vec<u8>, width: i64, height: i64) -> Result<Vec<i64>, String> {
    if width <= 0 || height <= 0 {
        return Err("ValueError: 尺寸必须为正整数".to_string());
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
    let mut seen = vec![false; w * h];
    let mut components: Vec<Component> = Vec::new();
    let mut stack: Vec<usize> = Vec::new();

    for start in 0..w * h {
        if seen[start] || data[start * 4 + 3] <= ALPHA_THRESHOLD {
            continue;
        }
        seen[start] = true;
        stack.push(start);
        let mut component = Component {
            size: 0,
            x1: w,
            y1: h,
            x2: 0,
            y2: 0,
        };
        while let Some(pixel) = stack.pop() {
            let x = pixel % w;
            let y = pixel / w;
            component.size += 1;
            component.x1 = component.x1.min(x);
            component.y1 = component.y1.min(y);
            component.x2 = component.x2.max(x);
            component.y2 = component.y2.max(y);

            // 4 邻接,与 scipy.ndimage.label 的默认结构一致。
            let neighbours = [
                (x > 0).then(|| pixel - 1),
                (x + 1 < w).then(|| pixel + 1),
                (y > 0).then(|| pixel - w),
                (y + 1 < h).then(|| pixel + w),
            ];
            for neighbour in neighbours.into_iter().flatten() {
                if !seen[neighbour] && data[neighbour * 4 + 3] > ALPHA_THRESHOLD {
                    seen[neighbour] = true;
                    stack.push(neighbour);
                }
            }
        }
        components.push(component);
    }

    if components.is_empty() {
        return Ok(Vec::new());
    }
    let max_size = components
        .iter()
        .map(|component| component.size)
        .max()
        .unwrap_or(0) as f64;

    let mut boxes: Vec<(i64, i64, i64, i64)> = components
        .iter()
        .filter(|component| {
            let size = component.size as f64;
            !(size < MIN_ICON_PIXELS as f64 || (max_size > 0.0 && size < 0.02 * max_size))
        })
        .map(|component| {
            (
                component.x1 as i64,
                component.y1 as i64,
                component.x2 as i64,
                component.y2 as i64,
            )
        })
        .collect();
    boxes.sort_by_key(|box_| (box_.1, box_.0, box_.3, box_.2));

    let mut out = Vec::with_capacity(boxes.len() * 4);
    for (x1, y1, x2, y2) in boxes {
        out.extend([x1, y1, x2, y2]);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 生成 width×height 的透明 RGBA,并在给定矩形内写入不透明像素。
    fn canvas(width: usize, height: usize, rects: &[(usize, usize, usize, usize)]) -> Vec<u8> {
        let mut data = vec![0u8; width * height * 4];
        for &(x1, y1, x2, y2) in rects {
            for y in y1..=y2 {
                for x in x1..=x2 {
                    data[(y * width + x) * 4 + 3] = 255;
                }
            }
        }
        data
    }

    #[test]
    fn two_blocks_are_sorted_by_row_then_column() {
        let data = canvas(60, 60, &[(34, 34, 58, 58), (4, 4, 28, 28)]);
        assert_eq!(
            segment_component_boxes(data, 60, 60),
            Ok(vec![4, 4, 28, 28, 34, 34, 58, 58])
        );
    }

    #[test]
    fn small_blocks_are_filtered_out() {
        // 21×21=441 < 500 被滤掉,30×30=900 保留。
        let data = canvas(80, 80, &[(1, 1, 21, 21), (40, 40, 69, 69)]);
        assert_eq!(
            segment_component_boxes(data, 80, 80),
            Ok(vec![40, 40, 69, 69])
        );
    }

    #[test]
    fn two_percent_of_the_largest_component_is_filtered() {
        // 最大块 160×160=25600 → 2% = 512:506 被滤掉,600 保留。
        let data = canvas(
            186,
            186,
            &[(1, 1, 160, 160), (162, 1, 183, 23), (162, 30, 185, 54)],
        );
        assert_eq!(
            segment_component_boxes(data, 186, 186),
            Ok(vec![1, 1, 160, 160, 162, 30, 185, 54])
        );
    }

    #[test]
    fn rejects_bad_input_like_the_python_kernel() {
        assert_eq!(
            segment_component_boxes(vec![], 0, 1),
            Err("ValueError: 尺寸必须为正整数".to_string())
        );
        assert_eq!(
            segment_component_boxes(vec![1, 2, 3], 2, 2),
            Err("ValueError: 数据长度应为 16(2×2×4),实际 3".to_string())
        );
    }
}
