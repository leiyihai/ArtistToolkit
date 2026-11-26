//! 「图标批处理」页:抠图 → 拆图标 → 按裁切类型/尺寸导出。
//!
//! 对应 Electron 版 `tools/icon_export/frontend/view.js`(旧版图集拆分流程);
//! 布局按 `app/renderer/styles.css` 还原:卡片 + 分段选择 + chip + 日志卡。

use std::path::PathBuf;

use gpui_kit::*;
use gpui_kit::component::slider::{Slider, SliderState};
use gpui_kit::component::*;
use gpui_kit::prelude::FluentBuilder as _;
use serde_json::json;

use crate::thumbs::ThumbCache;
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

/// 顶部模式:旧版图集拆分 / AI 图集命名(与 Electron 版 `#mode-tabs` 一致)。
#[derive(Clone, Copy, PartialEq, Eq, Default)]
pub enum IconMode {
    #[default]
    Legacy,
    Ai,
}

/// 「AI 图集命名」模式的状态(`aiState`)。
pub struct AiNamingState {
    pub model: &'static str,
    pub clean_dir: String,
    pub named_dir: String,
    pub out_dir: String,
    pub crop: Crop,
    pub sizes: [bool; 4],
    pub corner: Entity<SliderState>,
    pub normalize: bool,
    pub running: bool,
    pub logs: Vec<String>,
}

impl AiNamingState {
    pub fn push_log(&mut self, text: impl Into<String>) {
        self.logs.push(text.into());
        if self.logs.len() > 300 {
            self.logs.drain(0..self.logs.len() - 300);
        }
    }
}

pub const SIZES: [u32; 4] = [32, 64, 128, 256];

/// 可选模型(与 tools/icon_export/core.py 的 MODELS 对应)。
pub const MODELS: [(&str, &str); 3] = [
    ("isnet-general-use", "通用(ISNet)"),
    ("u2net", "经典(U2Net)"),
    ("birefnet-general", "人像精细(BiRefNet)"),
];

pub struct IconExportState {
    pub paths: Vec<PathBuf>,
    pub out_dir: String,
    pub crop: Crop,
    pub sizes: [bool; 4],
    /// 圆角半径(1–64 px,以 128px 输出为基准),与原版滑杆一致。
    pub corner: Entity<SliderState>,
    pub normalize: bool,
    pub running: bool,
    pub logs: Vec<String>,
    pub thumbs: ThumbCache,
    pub mode: IconMode,
    pub model: &'static str,
    pub ai: AiNamingState,
}

impl IconExportState {
    pub fn new(_window: &mut Window, cx: &mut Context<Shell>) -> Self {
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
        let corner = cx.new(|_| {
            SliderState::new()
                .min(1.0)
                .max(64.0)
                .step(1.0)
                .default_value(18.0)
        });
        let mut ai_sizes = [false; 4];
        ai_sizes[2] = true;
        let ai = AiNamingState {
            model: MODELS[0].0,
            clean_dir: String::new(),
            named_dir: String::new(),
            out_dir: out_dir.clone(),
            crop: Crop::Original,
            sizes: ai_sizes,
            corner: cx.new(|_| {
                SliderState::new()
                    .min(1.0)
                    .max(64.0)
                    .step(1.0)
                    .default_value(18.0)
            }),
            normalize: false,
            running: false,
            logs: Vec::new(),
        };
        let mode = if cfg!(debug_assertions)
            && std::env::var("ATK_UI_ICON_MODE").ok().as_deref() == Some("ai")
        {
            IconMode::Ai
        } else {
            IconMode::Legacy
        };
        Self {
            mode,
            model: MODELS[0].0,
            ai,
            thumbs: ThumbCache::new(&paths),
            paths,
            out_dir,
            crop: Crop::Original,
            sizes,
            corner,
            normalize: false,
            running: false,
            logs: Vec::new(),
        }
    }

    /// 当前圆角半径(px),供界面显示与 `corner_ratio` 计算。
    pub fn corner_px(&self, cx: &App) -> u32 {
        self.corner.read(cx).value().start().round() as u32
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
        let corner_px = self.icon.corner.read(cx).value().start().round() as u32;
        let shell = cx.entity();
        let thumbs = widgets::thumb_grid(
            &self.icon.thumbs,
            &self.icon.paths,
            move |index, _event, _window, cx| {
                shell.update(cx, |this, cx| {
                    if index < this.icon.paths.len() {
                        this.icon.paths.remove(index);
                        cx.notify();
                    }
                });
            },
        )
        .into_any_element();

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
        let current_model = self.icon.model;
        let mut model_row = widgets::seg_container();
        for (index, (key, label)) in MODELS.iter().enumerate() {
            let key = *key;
            model_row = model_row.child(widgets::seg_item(
                ("icon-model", index),
                *label,
                current_model == key,
                !running,
                cx.listener(move |this, _, _, cx| {
                    this.icon.model = key;
                    cx.notify();
                }),
            ));
        }

        v_flex()
            .size_full()
            .min_h_0()
            .gap(px(16.))
            .id("icon-page")
            .on_drop(cx.listener(|this, paths: &ExternalPaths, _, cx| {
                this.accept_drop(crate::Tab::IconExport, paths.0.to_vec(), cx)
            }))
            .child(
                widgets::card()
                    .child(widgets::card_title("1 · 添加图片"))
                    .child(
                        widgets::dropzone(
                            "icon-drop",
                            "将图片拖到此处,或点击选择(PNG / JPG / WebP,可多张)",
                            self.drag_over,
                        )
                        .on_click(cx.listener(|this, _, _, cx| this.icon_pick_images(cx)))
                        .on_drag_move(cx.listener(|this, _: &DragMoveEvent<ExternalPaths>, _, cx| {
                            this.note_drag_hover(cx);
                        }))
                        .on_file_drop_exit(cx.listener(|this, _, _, cx| {
                            this.drag_over = false;
                            cx.notify();
                        })),
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
                    )
                    .child(div().mt(px(12.)).when(total > 0, |this| this.child(thumbs))),
            )
            .child(
                widgets::card()
                    .child(widgets::card_title("2 · 输出选项"))
                    .child(widgets::field("裁切类型").child(crop_seg))
                    .child(
                        widgets::field("圆角半径")
                            .mt(px(12.))
                            .child(
                                div()
                                    .flex_1()
                                    .min_w_0()
                                    .when(!rounded, |this| this.opacity(0.45))
                                    .child(
                                        Slider::new(&self.icon.corner)
                                            .horizontal()
                                            .disabled(!rounded),
                                    ),
                            )
                            .child(
                                div()
                                    .w(px(44.))
                                    .flex_none()
                                    .text_right()
                                    .text_size(px(13.))
                                    .font_weight(FontWeight::SEMIBOLD)
                                    .text_color(if rounded { theme::text() } else { theme::muted() })
                                    .child(format!("{corner_px}px")),
                            ),
                    )
                    .child(widgets::field("输出尺寸").mt(px(12.)).child(size_row))
                    .child(widgets::field("模型").mt(px(12.)).child(model_row).child(
                        div()
                            .text_size(px(12.))
                            .text_color(theme::muted())
                            .child("卡通/图集用通用更干净"),
                    ))
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


    /// 图标页入口:顶部分段(旧版 / AI)与对应面板。
    pub(crate) fn icon_page(&mut self, cx: &mut Context<Self>) -> impl IntoElement {
        let mode = self.icon.mode;
        let mut mode_seg = widgets::seg_container();
        for (index, item) in [IconMode::Legacy, IconMode::Ai].into_iter().enumerate() {
            let label = match item {
                IconMode::Legacy => "旧版图集拆分",
                IconMode::Ai => "AI 图集命名",
            };
            mode_seg = mode_seg.child(widgets::seg_item(
                ("icon-mode", index),
                label,
                mode == item,
                true,
                cx.listener(move |this, _, _, cx| {
                    this.icon.mode = item;
                    cx.notify();
                }),
            ));
        }
        let body = match mode {
            IconMode::Legacy => self.icon_view(cx).into_any_element(),
            IconMode::Ai => self.icon_ai_view(cx).into_any_element(),
        };
        v_flex().size_full().min_h_0().gap(px(16.)).child(mode_seg).child(body)
    }

    /// 「AI 图集命名」面板:三个文件夹 + 输出选项 + 日志。
    pub(crate) fn icon_ai_view(&mut self, cx: &mut Context<Self>) -> impl IntoElement {
        let running = self.icon.ai.running;
        let logs: Vec<String> = self
            .icon
            .ai
            .logs
            .iter()
            .rev()
            .take(16)
            .rev()
            .cloned()
            .collect();
        let clean = self.icon.ai.clean_dir.clone();
        let named = self.icon.ai.named_dir.clone();
        let out = self.icon.ai.out_dir.clone();
        let rounded = self.icon.ai.crop == Crop::RoundedSquare;
        let corner_px = self.icon.ai.corner.read(cx).value().start().round() as u32;

        let mut crop_seg = widgets::seg_container();
        for (index, crop) in Crop::ALL.into_iter().enumerate() {
            crop_seg = crop_seg.child(widgets::seg_item(
                ("ai-crop", index),
                crop.label(),
                self.icon.ai.crop == crop,
                !running,
                cx.listener(move |this, _, _, cx| {
                    this.icon.ai.crop = crop;
                    cx.notify();
                }),
            ));
        }

        let mut size_row = h_flex().gap(px(8.)).items_center();
        for (index, size) in SIZES.iter().enumerate() {
            let size = *size;
            size_row = size_row.child(widgets::chip(
                ("ai-size", index),
                format!("{size}×{size}"),
                self.icon.ai.sizes[index],
                !running,
                cx.listener(move |this, _, _, cx| {
                    if let Some(pos) = SIZES.iter().position(|value| *value == size) {
                        this.icon.ai.sizes[pos] = !this.icon.ai.sizes[pos];
                        cx.notify();
                    }
                }),
            ));
        }

        let normalize = self.icon.ai.normalize;
        let current_ai_model = self.icon.ai.model;
        let mut ai_model_row = widgets::seg_container();
        for (index, (key, label)) in MODELS.iter().enumerate() {
            let key = *key;
            ai_model_row = ai_model_row.child(widgets::seg_item(
                ("ai-model", index),
                *label,
                current_ai_model == key,
                !running,
                cx.listener(move |this, _, _, cx| {
                    this.icon.ai.model = key;
                    cx.notify();
                }),
            ));
        }

        v_flex()
            .size_full()
            .min_h_0()
            .gap(px(16.))
            .child(
                widgets::card()
                    .p(px(22.))
                    .child(
                        div()
                            .text_size(px(14.))
                            .font_weight(FontWeight::SEMIBOLD)
                            .child("AI 图集命名"),
                    )
                    .child(
                        div()
                            .mt(px(6.))
                            .text_size(px(13.))
                            .text_color(theme::muted())
                            .child("无文字版负责拆图,带名称版只用于识别。两个文件夹中的图集按相同文件名配对。"),
                    )
                    .child(
                        v_flex()
                            .mt(px(18.))
                            .gap(px(12.))
                            .child(self.ai_path_row("无文字图集", clean, "ai-pick-clean", 0, cx))
                            .child(self.ai_path_row("带名称图集", named, "ai-pick-named", 1, cx))
                            .child(self.ai_path_row("输出文件夹", out, "ai-pick-out", 2, cx)),
                    )
                    .child(
                        v_flex()
                            .mt(px(18.))
                            .pt(px(18.))
                            .gap(px(12.))
                            .border_t_1()
                            .border_color(theme::border())
                            .child(
                                div()
                                    .text_size(px(12.))
                                    .font_weight(FontWeight::SEMIBOLD)
                                    .text_color(theme::muted())
                                    .child("输出选项"),
                            )
                            .child(widgets::field("裁切类型").pl(px(116.)).child(crop_seg))
                            .child(
                                widgets::field("圆角半径")
                                    .pl(px(116.))
                                    .child(
                                        div()
                                            .flex_1()
                                            .min_w_0()
                                            .when(!rounded, |this| this.opacity(0.45))
                                            .child(
                                                Slider::new(&self.icon.ai.corner)
                                                    .horizontal()
                                                    .disabled(!rounded),
                                            ),
                                    )
                                    .child(
                                        div()
                                            .w(px(44.))
                                            .flex_none()
                                            .text_right()
                                            .text_size(px(13.))
                                            .font_weight(FontWeight::SEMIBOLD)
                                            .text_color(if rounded { theme::text() } else { theme::muted() })
                                            .child(format!("{corner_px}px")),
                                    ),
                            )
                            .child(widgets::field("输出尺寸").pl(px(116.)).child(size_row))
                            .child(widgets::field("模型").pl(px(116.)).child(ai_model_row))
                            .child(
                                h_flex()
                                    .pl(px(190.))
                                    .child(widgets::chip(
                                        "ai-normalize",
                                        "统一图标视觉大小",
                                        normalize,
                                        !running,
                                        cx.listener(|this, _, _, cx| {
                                            this.icon.ai.normalize = !this.icon.ai.normalize;
                                            cx.notify();
                                        }),
                                    )),
                            ),
                    ),
            )
            .child(widgets::runbar().child(widgets::button(
                "ai-run",
                if running { "处理中…" } else { "开始 AI 命名" },
                true,
                cx.listener(|this, _, _, cx| this.run_icon_ai(cx)),
            )))
            .child(
                widgets::card()
                    .child(widgets::card_title("运行日志"))
                    .child(widgets::log_panel(logs)),
            )
    }

    /// AI 面板里的一行:190px 标签 + 路径框 + 选择文件夹。
    fn ai_path_row(
        &self,
        label: &'static str,
        value: String,
        id: &'static str,
        target: usize,
        cx: &mut Context<Self>,
    ) -> impl IntoElement {
        let empty = value.is_empty();
        h_flex()
            .items_center()
            .gap(px(12.))
            .child(
                div()
                    .w(px(190.))
                    .flex_none()
                    .text_size(px(13.))
                    .font_weight(FontWeight::SEMIBOLD)
                    .child(label),
            )
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
                    .text_size(px(13.))
                    .text_color(if empty { theme::muted() } else { theme::muted() })
                    .overflow_hidden()
                    .child(if empty {
                        format!("选择{label}文件夹")
                    } else {
                        value
                    }),
            )
            .child(widgets::button(
                id,
                "选择文件夹",
                false,
                cx.listener(move |this, _, _, cx| this.ai_pick_dir(target, cx)),
            ))
    }

    pub(crate) fn ai_pick_dir(&mut self, target: usize, cx: &mut Context<Self>) {
        let (tx, rx) = smol::channel::unbounded();
        std::thread::spawn(move || {
            let dir = rfd::FileDialog::new().pick_folder();
            let _ = tx.send_blocking(dir);
        });
        cx.spawn(async move |this, cx| {
            if let Ok(Some(dir)) = rx.recv().await {
                let value = dir.display().to_string();
                let _ = this.update(cx, |shell, cx| {
                    match target {
                        0 => shell.icon.ai.clean_dir = value,
                        1 => shell.icon.ai.named_dir = value,
                        _ => shell.icon.ai.out_dir = value,
                    }
                    cx.notify();
                });
            }
        })
        .detach();
    }

    pub(crate) fn run_icon_ai(&mut self, cx: &mut Context<Self>) {
        if self.icon.ai.running {
            return;
        }
        let clean = self.icon.ai.clean_dir.clone();
        let named = self.icon.ai.named_dir.clone();
        let out = self.icon.ai.out_dir.clone();
        if clean.is_empty() || named.is_empty() || out.is_empty() {
            self.icon.ai.push_log("请填写三个文件夹路径。");
            cx.notify();
            return;
        }
        let sizes: Vec<u32> = SIZES
            .iter()
            .zip(self.icon.ai.sizes)
            .filter(|(_, on)| *on)
            .map(|(size, _)| *size)
            .collect();
        if sizes.is_empty() {
            self.icon.ai.push_log("请至少选择一个输出尺寸。");
            cx.notify();
            return;
        }
        let mut payload = json!({
            "clean_dir": clean,
            "named_dir": named,
            "out": out,
            "crop": self.icon.ai.crop.key(),
            "sizes": sizes,
            "normalize": self.icon.ai.normalize,
            "model": self.icon.ai.model,
        });
        if self.icon.ai.crop == Crop::RoundedSquare {
            let corner = self.icon.ai.corner.read(cx).value().start();
            payload["corner_ratio"] = json!(corner / 128.0);
        }
        self.send_job(crate::JobKind::IconAi, "icon_ai_process", payload);
        self.icon.ai.running = true;
        self.icon.ai.push_log("开始 AI 图集命名…");
        cx.notify();
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
            "model": self.icon.model,
        });
        if self.icon.crop == Crop::RoundedSquare {
            let corner = self.icon.corner.read(cx).value().start();
            payload["corner_ratio"] = json!(corner / 128.0);
        }
        let count = paths.len();
        self.send_job(crate::JobKind::IconExport, "icon_process", payload);
        self.icon.running = true;
        self.icon.push_log(format!("开始导出 {count} 张图集…"));
        cx.notify();
    }
}
