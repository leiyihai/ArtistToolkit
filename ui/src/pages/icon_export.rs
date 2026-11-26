//! 「图标批处理」页:抠图 → 拆图标 → 按裁切类型/尺寸导出。
//!
//! 对应 Electron 版 `tools/icon_export/frontend/view.js`(旧版图集拆分流程);
//! 布局按 `app/renderer/styles.css` 还原:卡片 + 分段选择 + chip + 日志卡。

use std::path::PathBuf;

use gpui_kit::component::*;
use gpui_kit::prelude::FluentBuilder as _;
use gpui_kit::*;
use serde_json::json;

use crate::{Shell, theme, widgets};

#[derive(Clone, Copy, PartialEq, Eq, Default)]
pub enum Crop {
    #[default]
    Original,
    Square,
    Circle,
    RoundedSquare,
}

impl Crop {
    const ALL: [Crop; 4] = [Crop::Original, Crop::Square, Crop::Circle, Crop::RoundedSquare];

    fn key(self) -> &'static str {
        match self {
            Crop::Original => "original",
            Crop::Square => "square",
            Crop::Circle => "circle",
            Crop::RoundedSquare => "rounded_square",
        }
    }

    fn label(self) -> &'static str {
        match self {
            Crop::Original => "无(直接缩放)",
            Crop::Square => "方形",
            Crop::Circle => "正圆",
            Crop::RoundedSquare => "圆角方形",
        }
    }
}

pub const SIZES: [u32; 4] = [32, 64, 128, 256];
/// 圆角半径预设(px,以 128px 输出为基准);Electron 版是 1–64 的滑杆。
pub const CORNERS: [u32; 4] = [12, 18, 24, 32];

pub struct IconExportState {
    pub paths: Vec<PathBuf>,
    pub out_dir: String,
    pub crop: Crop,
    pub sizes: [bool; 4],
    pub corner_px: u32,
    pub normalize: bool,
    pub running: bool,
    pub logs: Vec<String>,
}

impl Default for IconExportState {
    fn default() -> Self {
        let home = std::env::var("USERPROFILE").unwrap_or_default();
        let desktop = PathBuf::from(&home).join("Desktop");
        let out_dir = if desktop.is_dir() {
            desktop.display().to_string()
        } else {
            home
        };
        let mut sizes = [false; 4];
        sizes[2] = true; // 默认 128×128,与 Electron 版一致
        let paths = if cfg!(debug_assertions) {
            std::env::var("ATK_UI_IMAGES")
                .map(|value| {
                    value
                        .split(';')
                        .filter(|part| !part.is_empty())
                        .map(PathBuf::from)
                        .collect()
                })
                .unwrap_or_default()
        } else {
            Vec::new()
        };
        Self {
            paths,
            out_dir,
            crop: Crop::Original,
            sizes,
            corner_px: 18,
            normalize: false,
            running: false,
            logs: Vec::new(),
        }
    }
}

impl IconExportState {
    pub fn push_log(&mut self, text: impl Into<String>) {
        self.logs.push(text.into());
        if self.logs.len() > 300 {
            self.logs.drain(0..self.logs.len() - 300);
        }
    }

    fn selected_sizes(&self) -> Vec<u32> {
        SIZES
            .iter()
            .zip(self.sizes)
            .filter(|(_, on)| *on)
            .map(|(size, _)| *size)
            .collect()
    }
}

impl Shell {
    pub(crate) fn icon_view(&mut self, cx: &mut Context<Self>) -> impl IntoElement {
        let running = self.icon.running;
        let picked = if self.icon.paths.is_empty() {
            "未选择图片".to_string()
        } else {
            format!("已选 {} 张", self.icon.paths.len())
        };
        let logs: Vec<String> = self
            .icon
            .logs
            .iter()
            .rev()
            .take(16)
            .rev()
            .cloned()
            .collect();
        let rounded = self.icon.crop == Crop::RoundedSquare;
        let total: usize = self.icon.paths.len();

        // 分段选择:裁切类型
        let mut crop_seg = widgets::seg_container();
        for (index, crop) in Crop::ALL.into_iter().enumerate() {
            crop_seg = crop_seg.child(widgets::seg_item(
                ("crop", index),
                crop.label(),
                self.icon.crop == crop,
                !running,
                cx.listener(move |this, _, _, cx| {
                    this.icon.crop = crop;
                    cx.notify();
                }),
            ));
        }

        // 圆角半径:Electron 是滑杆,这里用同宽的 chip 组承担同一参数
        let mut corner_row = h_flex().gap(px(8.)).items_center();
        for (index, px_value) in CORNERS.into_iter().enumerate() {
            corner_row = corner_row.child(widgets::chip(
                ("corner", index),
                format!("{px_value}px"),
                self.icon.corner_px == px_value,
                !running && rounded,
                cx.listener(move |this, _, _, cx| {
                    this.icon.corner_px = px_value;
                    cx.notify();
                }),
            ));
        }

        // 输出尺寸:多选 chip
        let mut size_row = h_flex().gap(px(8.)).items_center();
        for (index, size) in SIZES.iter().enumerate() {
            let size = *size;
            size_row = size_row.child(widgets::chip(
                ("size", index),
                format!("{size}×{size}"),
                self.icon.sizes[index],
                !running,
                cx.listener(move |this, _, _, cx| {
                    if let Some(pos) = SIZES.iter().position(|value| *value == size) {
                        this.icon.sizes[pos] = !this.icon.sizes[pos];
                        cx.notify();
                    }
                }),
            ));
        }

        let out_dir = self.icon.out_dir.clone();
        let normalize = self.icon.normalize;

        v_flex()
            .size_full()
            .min_h_0()
            .gap(px(16.))
            .child(
                widgets::card()
                    .child(widgets::card_title("1 · 添加图片"))
                    .child(
                        widgets::dropzone(
                            "icon-drop",
                            "将图片拖到此处,或点击选择(PNG / JPG / WebP,可多张)",
                        )
                        .on_click(cx.listener(|this, _, _, cx| this.icon_pick_images(cx))),
                    )
                    .child(
                        h_flex()
                            .mt(px(12.))
                            .gap(px(10.))
                            .items_center()
                            .child(widgets::button(
                                "icon-pick",
                                "选择图片…",
                                false,
                                cx.listener(|this, _, _, cx| this.icon_pick_images(cx)),
                            ))
                            .child(widgets::button(
                                "icon-clear",
                                "清空",
                                false,
                                cx.listener(|this, _, _, cx| {
                                    this.icon.paths.clear();
                                    cx.notify();
                                }),
                            ))
                            .child(
                                div()
                                    .text_size(px(12.))
                                    .text_color(theme::muted())
                                    .child(picked),
                            ),
                    ),
            )
            .child(
                widgets::card()
                    .child(widgets::card_title("2 · 输出选项"))
                    .child(widgets::field("裁切类型").child(crop_seg))
                    .child(
                        widgets::field("圆角半径")
                            .mt(px(12.))
                            .child(corner_row)
                            .child(
                                div()
                                    .text_size(px(13.))
                                    .font_weight(FontWeight::SEMIBOLD)
                                    .text_color(if rounded { theme::text() } else { theme::muted() })
                                    .child(format!("{}px", self.icon.corner_px)),
                            ),
                    )
                    .child(widgets::field("输出尺寸").mt(px(12.)).child(size_row))
                    .child(
                        widgets::field("输出路径")
                            .mt(px(12.))
                            .child(
                                div()
                                    .flex_1()
                                    .min_w_0()
                                    .px(px(10.))
                                    .py(px(8.))
                                    .rounded(px(theme::RADIUS))
                                    .border_1()
                                    .border_color(theme::border())
                                    .bg(theme::panel())
                                    .text_size(px(12.))
                                    .text_color(theme::muted())
                                    .overflow_hidden()
                                    .child(out_dir),
                            )
                            .child(widgets::button(
                                "icon-out",
                                "浏览…",
                                false,
                                cx.listener(|this, _, _, cx| this.icon_pick_output_dir(cx)),
                            )),
                    )
                    .child(
                        h_flex()
                            .mt(px(12.))
                            .pl(px(84.))
                            .child(widgets::chip(
                                "icon-normalize",
                                "统一图标视觉大小",
                                normalize,
                                !running,
                                cx.listener(|this, _, _, cx| {
                                    this.icon.normalize = !this.icon.normalize;
                                    cx.notify();
                                }),
                            )),
                    ),
            )
            .child(
                widgets::runbar().child(widgets::button(
                    "icon-run",
                    if running { "处理中…" } else { "开始导出" },
                    true,
                    cx.listener(|this, _, _, cx| this.run_icon_export(cx)),
                )),
            )
            .child(
                widgets::card()
                    .child(widgets::card_title("运行日志"))
                    .child(widgets::log_panel(logs)),
            )
            .when(total == 0, |this| this)
    }

    pub(crate) fn icon_pick_images(&mut self, cx: &mut Context<Self>) {
        let (tx, rx) = smol::channel::unbounded();
        std::thread::spawn(move || {
            let files = rfd::FileDialog::new()
                .add_filter("图片", &["png", "jpg", "jpeg", "webp"])
                .pick_files();
            let _ = tx.send_blocking(files);
        });
        cx.spawn(async move |this, cx| {
            if let Ok(Some(files)) = rx.recv().await {
                let _ = this.update(cx, |shell, cx| {
                    shell.icon.paths = files;
                    let count = shell.icon.paths.len();
                    shell.icon.push_log(format!("已选择 {count} 张图片"));
                    cx.notify();
                });
            }
        })
        .detach();
    }

    pub(crate) fn icon_pick_output_dir(&mut self, cx: &mut Context<Self>) {
        let (tx, rx) = smol::channel::unbounded();
        std::thread::spawn(move || {
            let dir = rfd::FileDialog::new().pick_folder();
            let _ = tx.send_blocking(dir);
        });
        cx.spawn(async move |this, cx| {
            if let Ok(Some(dir)) = rx.recv().await {
                let _ = this.update(cx, |shell, cx| {
                    shell.icon.out_dir = dir.display().to_string();
                    cx.notify();
                });
            }
        })
        .detach();
    }

    pub(crate) fn run_icon_export(&mut self, cx: &mut Context<Self>) {
        if self.icon.paths.is_empty() || self.icon.running {
            return;
        }
        let sizes = self.icon.selected_sizes();
        if sizes.is_empty() {
            self.icon.push_log("请至少选择一个输出尺寸。");
            cx.notify();
            return;
        }
        let paths: Vec<String> = self
            .icon
            .paths
            .iter()
            .map(|path| path.display().to_string())
            .collect();
        let mut payload = json!({
            "paths": paths,
            "crop": self.icon.crop.key(),
            "sizes": sizes,
            "out": self.icon.out_dir,
            "normalize": self.icon.normalize,
        });
        if self.icon.crop == Crop::RoundedSquare {
            payload["corner_ratio"] = json!(self.icon.corner_px as f64 / 128.0);
        }
        let count = paths.len();
        self.send_job(crate::JobKind::IconExport, "icon_process", payload);
        self.icon.running = true;
        self.icon.push_log(format!("开始导出 {count} 张图集…"));
        cx.notify();
    }
}
