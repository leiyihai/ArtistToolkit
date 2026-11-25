//! 「AI 抠图」页:图片一键去背景,输出透明 PNG。
//!
//! 对应 Electron 版 `tools/ai_matting/frontend/view.js`;后端命令 `matting_process`。

use std::path::PathBuf;

use gpui_kit::component::{button::Button, button::ButtonVariants, progress::Progress, *};
use gpui_kit::*;
use serde_json::json;

use crate::Shell;

pub struct AiMattingState {
    pub paths: Vec<PathBuf>,
    pub out_dir: String,
    pub running: bool,
    pub progress: (u64, u64),
    pub logs: Vec<String>,
}

impl Default for AiMattingState {
    fn default() -> Self {
        let home = std::env::var("USERPROFILE").unwrap_or_default();
        let desktop = PathBuf::from(&home).join("Desktop");
        let out_dir = if desktop.is_dir() {
            desktop.display().to_string()
        } else {
            home
        };
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
            running: false,
            progress: (0, 0),
            logs: Vec::new(),
        }
    }
}

impl AiMattingState {
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

impl Shell {
    pub(crate) fn matting_view(&mut self, cx: &mut Context<Self>) -> impl IntoElement {
        let theme = cx.theme().clone();
        let running = self.matting.running;
        let picked = if self.matting.paths.is_empty() {
            "未选择图片".to_string()
        } else {
            format!("已选 {} 张", self.matting.paths.len())
        };
        let progress = self.matting.progress;
        let percent = self.matting.percent();
        let logs: Vec<String> = self
            .matting
            .logs
            .iter()
            .rev()
            .take(16)
            .rev()
            .cloned()
            .collect();

        v_flex()
            .size_full()
            .min_h_0()
            .gap_3()
            .p_4()
            .id("matting-page")
            .on_drop(cx.listener(|this, paths: &ExternalPaths, _, cx| {
                this.accept_drop(crate::Tab::AiMatting, paths.0.to_vec(), cx)
            }))
            .child(self.drop_banner(
                &theme,
                "拖拽图片到这里(PNG / JPG / WebP,可多张),或点「选择图片…」",
            ))
            .child(
                h_flex()
                    .gap_2()
                    .items_center()
                    .child(
                        Button::new("matting-pick")
                            .label("选择图片…")
                            .disabled(running)
                            .on_click(cx.listener(|this, _, _, cx| this.matting_pick_images(cx))),
                    )
                    .child(
                        div()
                            .text_sm()
                            .text_color(theme.muted_foreground)
                            .child(picked),
                    )
                    .child(
                        Button::new("matting-clear")
                            .label("清空")
                            .small()
                            .disabled(running || self.matting.paths.is_empty())
                            .on_click(cx.listener(|this, _, _, cx| {
                                this.matting.paths.clear();
                                cx.notify();
                            })),
                    )
                    .child(div().flex_1())
                    .child(
                        Button::new("matting-out")
                            .label("输出目录…")
                            .disabled(running)
                            .on_click(cx.listener(|this, _, _, cx| this.matting_pick_output_dir(cx))),
                    )
                    .child(
                        div()
                            .max_w(px(360.))
                            .overflow_hidden()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child(self.matting.out_dir.clone()),
                    ),
            )
            .child(
                div()
                    .text_xs()
                    .text_color(theme.muted_foreground)
                    .child("首次使用会加载模型(约 1GB);有 GPU 自动加速,否则用 CPU。"),
            )
            .child(
                h_flex()
                    .gap_3()
                    .items_center()
                    .child(
                        Button::new("matting-run")
                            .primary()
                            .label(if running { "处理中…" } else { "开始抠图" })
                            .disabled(running || self.matting.paths.is_empty())
                            .on_click(cx.listener(|this, _, _, cx| this.run_matting(cx))),
                    )
                    .child(
                        div()
                            .flex_1()
                            .child(Progress::new("matting-progress").value(percent)),
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

    pub(crate) fn matting_pick_images(&mut self, cx: &mut Context<Self>) {
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
                    shell.matting.paths = files;
                    let count = shell.matting.paths.len();
                    shell.matting.push_log(format!("已选择 {count} 张图片"));
                    cx.notify();
                });
            }
        })
        .detach();
    }

    pub(crate) fn matting_pick_output_dir(&mut self, cx: &mut Context<Self>) {
        let (tx, rx) = smol::channel::unbounded();
        std::thread::spawn(move || {
            let dir = rfd::FileDialog::new().pick_folder();
            let _ = tx.send_blocking(dir);
        });
        cx.spawn(async move |this, cx| {
            if let Ok(Some(dir)) = rx.recv().await {
                let _ = this.update(cx, |shell, cx| {
                    shell.matting.out_dir = dir.display().to_string();
                    cx.notify();
                });
            }
        })
        .detach();
    }

    pub(crate) fn run_matting(&mut self, cx: &mut Context<Self>) {
        if self.matting.paths.is_empty() || self.matting.running {
            return;
        }
        let paths: Vec<String> = self
            .matting
            .paths
            .iter()
            .map(|path| path.display().to_string())
            .collect();
        let count = paths.len();
        self.send_job(
            crate::JobKind::Matting,
            "matting_process",
            json!({ "paths": paths, "out": self.matting.out_dir }),
        );
        self.matting.running = true;
        self.matting.progress = (0, count as u64);
        self.matting.push_log(format!("开始抠图 {count} 张…"));
        cx.notify();
    }
}
