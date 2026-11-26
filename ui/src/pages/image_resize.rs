//! 「批量缩放」页:递归扫描 → 按目标尺寸缩放 → 保持目录结构输出,可取消。
//!
//! 对应 Electron 版 `tools/image_resize/frontend/view.js`;后端命令 `resize_process`
//! 与 `resize_cancel`。

use gpui_kit::component::{input::{Input, InputState}, *};
use gpui_kit::*;
use serde_json::json;

use crate::{Shell, theme, widgets};

/// 目标尺寸预设,与 Electron 版一致。
pub const PRESETS: [(u32, u32); 7] = [
    (64, 64),
    (128, 128),
    (256, 256),
    (512, 512),
    (800, 600),
    (1024, 768),
    (1920, 1080),
];

/// 自定义输入框:去掉组件自带外观,套一层与 `.text-input` 相同的边框。
fn input_box(state: &Entity<InputState>, width: f32) -> impl IntoElement {
    div()
        .w(px(width))
        .px(px(10.))
        .py(px(6.))
        .rounded(px(theme::RADIUS))
        .border_1()
        .border_color(theme::border())
        .bg(theme::panel())
        .child(Input::new(state).appearance(false))
}

pub struct ImageResizeState {
    pub input_dir: String,
    pub output_dir: String,
    pub width: Entity<InputState>,
    pub height: Entity<InputState>,
    pub keep_ratio: bool,
    pub running: bool,
    pub progress: (u64, u64),
    pub logs: Vec<String>,
}

impl ImageResizeState {
    pub fn new(window: &mut Window, cx: &mut Context<Shell>) -> Self {
        let home = std::env::var("USERPROFILE").unwrap_or_default();
        let desktop = std::path::PathBuf::from(&home).join("Desktop");
        let output_dir = if desktop.is_dir() {
            desktop.display().to_string()
        } else {
            home
        };
        let width = cx.new(|cx| InputState::new(window, cx).default_value("1024").placeholder("宽"));
        let height = cx.new(|cx| InputState::new(window, cx).default_value("1024").placeholder("高"));
        // 开发期自动化:ATK_UI_RESIZE_IN 预填输入目录(仅 debug 构建生效)。
        let input_dir = if cfg!(debug_assertions) {
            std::env::var("ATK_UI_RESIZE_IN").unwrap_or_default()
        } else {
            String::new()
        };
        Self {
            input_dir,
            output_dir,
            width,
            height,
            keep_ratio: false,
            running: false,
            progress: (0, 0),
            logs: Vec::new(),
        }
    }

    pub fn push_log(&mut self, text: impl Into<String>) {
        self.logs.push(text.into());
        if self.logs.len() > 300 {
            self.logs.drain(0..self.logs.len() - 300);
        }
    }

}

fn parse_size(value: &str) -> Option<i64> {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return None;
    }
    match trimmed.parse::<i64>() {
        Ok(size) if size > 0 => Some(size),
        _ => None,
    }
}

impl Shell {
    pub(crate) fn resize_view(&mut self, cx: &mut Context<Self>) -> impl IntoElement {
        let running = self.resize.running;
        let logs: Vec<String> = self
            .resize
            .logs
            .iter()
            .rev()
            .take(16)
            .rev()
            .cloned()
            .collect();
        let input_dir = self.resize.input_dir.clone();
        let out_dir = self.resize.output_dir.clone();
        let keep_ratio = self.resize.keep_ratio;
        let width_value = self.resize.width.read(cx).value().to_string();
        let height_value = self.resize.height.read(cx).value().to_string();

        let mut preset_row = h_flex().gap(px(8.)).items_center();
        for (index, (w, h)) in PRESETS.iter().enumerate() {
            let (w, h) = (*w, *h);
            let active = width_value.trim() == w.to_string() && height_value.trim() == h.to_string();
            preset_row = preset_row.child(widgets::chip(
                ("resize-preset", index),
                format!("{w}×{h}"),
                active,
                !running,
                cx.listener(move |this, _, window, cx| {
                    this.resize
                        .width
                        .update(cx, |state, cx| state.set_value(w.to_string(), window, cx));
                    this.resize
                        .height
                        .update(cx, |state, cx| state.set_value(h.to_string(), window, cx));
                    cx.notify();
                }),
            ));
        }

        v_flex()
            .size_full()
            .min_h_0()
            .gap(px(16.))
            .id("resize-page")
            .on_drop(cx.listener(|this, paths: &ExternalPaths, _, cx| {
                this.accept_drop(crate::Tab::ImageResize, paths.0.to_vec(), cx)
            }))
            .child(
                widgets::card()
                    .child(widgets::card_title("1 · 输入文件夹"))
                    .child(
                        widgets::dropzone(
                            "resize-drop",
                            "将文件夹拖到此处,或点击选择",
                            self.drag_over,
                        )
                            .on_click(cx.listener(|this, _, _, cx| this.resize_pick_dir(true, cx)))
                        .on_drag_move(cx.listener(|this, _: &DragMoveEvent<ExternalPaths>, _, cx| {
                            this.note_drag_hover(cx);
                        }))
                        .on_file_drop_exit(cx.listener(|this, _, _, cx| {
                            this.drag_over = false;
                            cx.notify();
                        })),
                    )
                    .child(
                        div()
                            .mt(px(10.))
                            .px(px(10.))
                            .py(px(8.))
                            .rounded(px(8.))
                            .bg(theme::panel_2())
                            .text_size(px(12.))
                            .text_color(if input_dir.is_empty() {
                                theme::muted()
                            } else {
                                theme::text()
                            })
                            .overflow_hidden()
                            .child(if input_dir.is_empty() {
                                "未选择输入文件夹".to_string()
                            } else {
                                input_dir
                            }),
                    ),
            )
            .child(
                widgets::card()
                    .child(widgets::card_title("2 · 输出文件夹"))
                    .child(
                        widgets::field("输出路径")
                            .child(
                                h_flex()
                                    .flex_1()
                                    .min_w_0()
                                    .items_center()
                                    .gap(px(10.))
                                    .child(widgets::path_box(out_dir, true))
                                    .child(widgets::button(
                                        "resize-out",
                                        "浏览…",
                                        false,
                                        cx.listener(|this, _, _, cx| {
                                            this.resize_pick_dir(false, cx)
                                        }),
                                    )),
                            ),
                    ),
            )
            .child(
                widgets::card()
                    .child(widgets::card_title("3 · 目标尺寸"))
                    .child(widgets::field("预设").child(preset_row))
                    .child(
                        widgets::field("自定义")
                            .mt(px(12.))
                            .child(input_box(&self.resize.width, 90.0))
                            .child(div().text_size(px(12.)).text_color(theme::muted()).child("×"))
                            .child(input_box(&self.resize.height, 90.0))
                            .child(div().text_size(px(12.)).text_color(theme::muted()).child("像素"))
                            .child(widgets::check_chip(
                                "resize-ratio",
                                "等比例(透明画布居中)",
                                keep_ratio,
                                !running,
                                cx.listener(|this, _, _, cx| {
                                    this.resize.keep_ratio = !this.resize.keep_ratio;
                                    cx.notify();
                                }),
                            )),
                    ),
            )
            .child(
                widgets::runbar()
                    .child(widgets::button(
                        "resize-cancel",
                        "取消",
                        false,
                        cx.listener(|this, _, _, cx| {
                            this.send_job(crate::JobKind::Resize, "resize_cancel", json!({}));
                            this.resize.push_log("已请求取消…");
                            cx.notify();
                        }),
                    ))
                    .child(widgets::button(
                        "resize-run",
                        if running { "处理中…" } else { "开始缩放" },
                        true,
                        cx.listener(|this, _, _, cx| this.run_resize(cx)),
                    )),
            )
            .child(
                widgets::card()
                    .child(widgets::card_title("运行日志"))
                    .child(widgets::log_panel(logs)),
            )
    }
    pub(crate) fn resize_pick_dir(&mut self, input: bool, cx: &mut Context<Self>) {
        let (tx, rx) = smol::channel::unbounded();
        std::thread::spawn(move || {
            let dir = rfd::FileDialog::new().pick_folder();
            let _ = tx.send_blocking(dir);
        });
        cx.spawn(async move |this, cx| {
            if let Ok(Some(dir)) = rx.recv().await {
                let _ = this.update(cx, |shell, cx| {
                    if input {
                        shell.resize.input_dir = dir.display().to_string();
                    } else {
                        shell.resize.output_dir = dir.display().to_string();
                    }
                    cx.notify();
                });
            }
        })
        .detach();
    }

    pub(crate) fn run_resize(&mut self, cx: &mut Context<Self>) {
        if self.resize.input_dir.is_empty() || self.resize.running {
            return;
        }
        let width = parse_size(self.resize.width.read(cx).value().as_ref());
        let height = parse_size(self.resize.height.read(cx).value().as_ref());
        let (Some(width), Some(height)) = (width, height) else {
            self.resize.push_log("尺寸必须是正整数。");
            cx.notify();
            return;
        };
        let payload = json!({
            "input": self.resize.input_dir,
            "output": self.resize.output_dir,
            "width": width,
            "height": height,
            "keep_ratio": self.resize.keep_ratio,
        });
        self.send_job(crate::JobKind::Resize, "resize_process", payload);
        self.resize.running = true;
        self.resize.progress = (0, 0);
        self.resize
            .push_log(format!("开始缩放到 {width}×{height}…"));
        cx.notify();
    }
}

