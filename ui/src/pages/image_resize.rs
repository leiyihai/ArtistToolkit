//! 「批量缩放」页:递归扫描 → 按目标尺寸缩放 → 保持目录结构输出,可取消。
//!
//! 对应 Electron 版 `tools/image_resize/frontend/view.js`;后端命令 `resize_process`
//! 与 `resize_cancel`。

use gpui_kit::component::{
    button::Button, button::ButtonVariants, checkbox::Checkbox, input::{Input, InputState},
    progress::Progress, *,
};
use gpui_kit::*;
use serde_json::json;

use crate::Shell;

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

    fn percent(&self) -> f32 {
        let (done, total) = self.progress;
        if total == 0 {
            0.0
        } else {
            (done as f32 / total as f32) * 100.0
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
        let theme = cx.theme().clone();
        let running = self.resize.running;
        let progress = self.resize.progress;
        let percent = self.resize.percent();
        let logs: Vec<String> = self
            .resize
            .logs
            .iter()
            .rev()
            .take(16)
            .rev()
            .cloned()
            .collect();
        let input_dir = if self.resize.input_dir.is_empty() {
            "未选择输入目录".to_string()
        } else {
            self.resize.input_dir.clone()
        };

        v_flex()
            .size_full()
            .min_h_0()
            .gap_3()
            .p_4()
            .id("resize-page")
            .on_drop(cx.listener(|this, paths: &ExternalPaths, _, cx| {
                this.accept_drop(crate::Tab::ImageResize, paths.0.to_vec(), cx)
            }))
            .child(self.drop_banner(
                &theme,
                "拖拽文件夹到这里作为输入目录,或点「输入目录…」",
            ))
            .child(
                h_flex()
                    .gap_2()
                    .items_center()
                    .child(
                        Button::new("resize-in")
                            .label("输入目录…")
                            .disabled(running)
                            .on_click(cx.listener(|this, _, _, cx| this.resize_pick_dir(true, cx))),
                    )
                    .child(
                        div()
                            .max_w(px(420.))
                            .overflow_hidden()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child(input_dir),
                    )
                    .child(div().flex_1())
                    .child(
                        Button::new("resize-out")
                            .label("输出目录…")
                            .disabled(running)
                            .on_click(cx.listener(|this, _, _, cx| this.resize_pick_dir(false, cx))),
                    )
                    .child(
                        div()
                            .max_w(px(360.))
                            .overflow_hidden()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child(self.resize.output_dir.clone()),
                    ),
            )
            .child(
                h_flex()
                    .gap_2()
                    .items_center()
                    .child(div().text_sm().child("目标尺寸:"))
                    .child(div().w(px(120.)).child(Input::new(&self.resize.width)))
                    .child(div().text_sm().child("×"))
                    .child(div().w(px(120.)).child(Input::new(&self.resize.height)))
                    .child(
                        Checkbox::new("resize-ratio")
                            .label("等比例居中(否则拉伸填满)")
                            .checked(self.resize.keep_ratio)
                            .disabled(running)
                            .on_change(cx.listener(|this, checked, _, cx| {
                                this.resize.keep_ratio = *checked;
                                cx.notify();
                            })),
                    ),
            )
            .child(
                h_flex()
                    .gap_3()
                    .items_center()
                    .child(
                        Button::new("resize-run")
                            .primary()
                            .label(if running { "处理中…" } else { "开始缩放" })
                            .disabled(running || self.resize.input_dir.is_empty())
                            .on_click(cx.listener(|this, _, _, cx| this.run_resize(cx))),
                    )
                    .child(
                        Button::new("resize-cancel")
                            .label("取消")
                            .disabled(!running)
                            .on_click(cx.listener(|this, _, _, cx| {
                                this.send_job(crate::JobKind::Resize, "resize_cancel", json!({}));
                                this.resize.push_log("已请求取消…");
                                cx.notify();
                            })),
                    )
                    .child(
                        div()
                            .flex_1()
                            .child(Progress::new("resize-progress").value(percent)),
                    )
                    .child(
                        div()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child(if progress.1 == 0 {
                                String::new()
                            } else {
                                format!("{}/{}", progress.0, progress.1)
                            }),
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

