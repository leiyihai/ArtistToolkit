//! 「图标批处理」页:抠图 → 拆图标 → 按裁切类型/尺寸导出。
//!
//! 对应 Electron 版 `tools/icon_export/frontend/view.js`(旧版图集拆分流程);
//! 后端命令 `icon_process`,连通域拆分已由 `rust/icon-export-rs` 加速。

use std::path::PathBuf;

use gpui_kit::component::{button::Button, button::ButtonVariants, checkbox::Checkbox, progress::Progress, *};
use gpui_kit::*;
use serde_json::json;

use crate::Shell;

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

pub struct IconExportState {
    pub paths: Vec<PathBuf>,
    pub out_dir: String,
    pub crop: Crop,
    pub sizes: [bool; 4],
    /// 圆角半径(px,以 128px 输出为基准),与 Electron 版一致。
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
        // 开发期自动化:ATK_UI_IMAGES="a.png;b.png" 预填图片路径(仅 debug 构建生效)。
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
        let theme = cx.theme().clone();
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

        v_flex()
            .size_full()
            .min_h_0()
            .gap_3()
            .p_4()
            .child(
                h_flex()
                    .gap_2()
                    .items_center()
                    .child(
                        Button::new("icon-pick")
                            .label("选择图片…")
                            .disabled(running)
                            .on_click(cx.listener(|this, _, _, cx| this.icon_pick_images(cx))),
                    )
                    .child(
                        div()
                            .text_sm()
                            .text_color(theme.muted_foreground)
                            .child(picked),
                    )
                    .child(
                        Button::new("icon-clear")
                            .label("清空")
                            .small()
                            .disabled(running || self.icon.paths.is_empty())
                            .on_click(cx.listener(|this, _, _, cx| {
                                this.icon.paths.clear();
                                cx.notify();
                            })),
                    )
                    .child(div().flex_1())
                    .child(
                        Button::new("icon-out")
                            .label("输出目录…")
                            .disabled(running)
                            .on_click(cx.listener(|this, _, _, cx| this.icon_pick_output_dir(cx))),
                    )
                    .child(
                        div()
                            .max_w(px(360.))
                            .overflow_hidden()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child(self.icon.out_dir.clone()),
                    ),
            )
            .child(
                h_flex()
                    .gap_2()
                    .items_center()
                    .child(div().text_sm().child("裁切类型:"))
                    .children(Crop::ALL.map(|crop| {
                        Button::new(format!("crop-{}", crop.key()))
                            .label(crop.label())
                            .small()
                            .selected(self.icon.crop == crop)
                            .disabled(running)
                            .on_click(cx.listener(move |this, _, _, cx| {
                                this.icon.crop = crop;
                                cx.notify();
                            }))
                    })),
            )
            .child(
                h_flex()
                    .gap_2()
                    .items_center()
                    .child(
                        div()
                            .text_sm()
                            .text_color(if rounded {
                                theme.foreground
                            } else {
                                theme.muted_foreground
                            })
                            .child("圆角半径(128px 基准):"),
                    )
                    .children([12_u32, 18, 24, 32].map(|px_value| {
                        Button::new(format!("corner-{px_value}"))
                            .label(format!("{px_value}px"))
                            .small()
                            .selected(self.icon.corner_px == px_value)
                            .disabled(running || !rounded)
                            .on_click(cx.listener(move |this, _, _, cx| {
                                this.icon.corner_px = px_value;
                                cx.notify();
                            }))
                    }))
                    .child(div().w(px(16.)))
                    .child(div().text_sm().child("输出尺寸:"))
                    .children(SIZES.iter().zip(self.icon.sizes).map(|(size, on)| {
                        let size = *size;
                        Button::new(format!("size-{size}"))
                            .label(format!("{size}×{size}"))
                            .small()
                            .selected(on)
                            .disabled(running)
                            .on_click(cx.listener(move |this, _, _, cx| {
                                if let Some(index) = SIZES.iter().position(|value| *value == size) {
                                    this.icon.sizes[index] = !this.icon.sizes[index];
                                    cx.notify();
                                }
                            }))
                    })),
            )
            .child(
                h_flex()
                    .gap_5()
                    .items_center()
                    .child(
                        Checkbox::new("icon-normalize")
                            .label("统一图标视觉大小")
                            .checked(self.icon.normalize)
                            .disabled(running)
                            .on_change(cx.listener(|this, checked, _, cx| {
                                this.icon.normalize = *checked;
                                cx.notify();
                            })),
                    )
                    .child(
                        div()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child("圆角半径 = 输出边长 × (px/128);裁切后按内容面积统一大小。"),
                    ),
            )
            .child(
                h_flex()
                    .gap_3()
                    .items_center()
                    .child(
                        Button::new("icon-run")
                            .primary()
                            .label(if running { "处理中…" } else { "开始导出" })
                            .disabled(
                                running
                                    || self.icon.paths.is_empty()
                                    || self.icon.selected_sizes().is_empty(),
                            )
                            .on_click(cx.listener(|this, _, _, cx| this.run_icon_export(cx))),
                    )
                    .child(
                        div()
                            .flex_1()
                            .child(Progress::new("icon-progress").loading(running).value(0.0)),
                    ),
            )
            .child(
                v_flex()
                    .flex_1()
                    .min_h_0()
                    .gap_1()
                    .p_3()
                    .rounded(theme.radius)
                    .border_1()
                    .border_color(theme.border)
                    .bg(theme.muted)
                    .overflow_hidden()
                    .children(logs.into_iter().map(|line| {
                        div()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child(line)
                    })),
            )
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
