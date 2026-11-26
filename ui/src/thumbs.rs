//! 缩略图缓存:选中的图片解码一次、缩到 128×96 以内,供列表显示。

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use gpui_kit::*;

#[derive(Default)]
pub struct ThumbCache {
    images: HashMap<PathBuf, Option<Arc<RenderImage>>>,
}

impl ThumbCache {
    pub fn new(paths: &[PathBuf]) -> Self {
        let mut cache = Self::default();
        cache.ensure(paths);
        cache
    }

    /// 确保这些路径都有缩略图(已缓存的不重复解码)。
    pub fn ensure(&mut self, paths: &[PathBuf]) {
        for path in paths {
            if !self.images.contains_key(path) {
                let image = load_thumb(path);
                self.images.insert(path.clone(), image);
            }
        }
    }

    pub fn get(&self, path: &Path) -> Option<Arc<RenderImage>> {
        self.images.get(path).cloned().flatten()
    }
}

/// 读图并缩到 128×96 以内(保持比例),失败时返回 None(界面退化为无图卡片)。
fn load_thumb(path: &Path) -> Option<Arc<RenderImage>> {
    let reader = image::ImageReader::open(path)
        .ok()?
        .with_guessed_format()
        .ok()?;
    let decoded = reader.decode().ok()?;
    let thumb = decoded.thumbnail(128, 96).to_rgba8();
    let frame = image::Frame::new(thumb);
    Some(Arc::new(RenderImage::new(vec![frame])))
}
