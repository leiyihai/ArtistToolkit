//! 「去底」页:选图 / 模式 / 去边 → 调后端 unmult_process → 日志与进度。
//!
//! 对应 Electron 版 `tools/unmult/frontend/view.js`;计算本身在 Python 侧,
//! 像素内核已是 Rust(`rust/unmult-rs`)。

use std::path::PathBuf;

use gpui_kit::component::{button::Button, button::ButtonVariants, checkbox::Checkbox, progress::Progress, *};
use gpui_kit::*;
use serde_json::json;

use crate::Shell;

#[derive(Clone, Copy, PartialEq, Eq, Default)]
pub enum Mode {
    #[default]
    Auto,
    Black,
    White,
}

impl Mode {
    fn key(self) -> &'static str {
        match self {
            Mode::Auto => "auto",
            Mode::Black => "black",
            Mode::White => "white",
        }
    }
    fn label(self) -> &'static str {
        match self {
            Mode::Auto => "自动判断",
            Mode::Black => "去黑底",
            Mode::White => "去白底",
        }
    }
}

pub struct UnmultState {
    pub paths: Vec<PathBuf>,
    pub out_dir: String,
    pub mode: Mode,
    pub defringe: f32,
    pub rebuild_alpha: bool,
    pub no_overwrite: bool,
    pub running: bool,
    pub progress: (u64, u64),
    pub logs: Vec<String>,
    pub job_id: Option<u64>,
}

impl Default for UnmultState {
    fn default() -> Self {
        let home = std::env::var("USERPROFILE").unwrap_or_default();
        let desktop = PathBuf::from(&home).join("Desktop");
        let out_dir = if desktop.is_dir() {
            desktop.display().to_string()
        } else {
            home
        };
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
            mode: Mode::Auto,
            defringe: 0.0,
            rebuild_alpha: false,
            no_overwrite: false,
            running: false,
            progress: (0, 0),
            logs: Vec::new(),
            job_id: None,
        }
    }
}

impl UnmultState {
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
    pub(crate) fn unmult_view(&mut self, cx: &mut Context<Self>) -> impl IntoElement {
        let theme = cx.theme().clone();
        let picked = if self.unmult.paths.is_empty() {
            "未选择图片".to_string()
        } else {
            format!("已选 {} 张", self.unmult.paths.len())
        };
        let running = self.unmult.running;
        let percent = self.unmult.percent();
        let logs: Vec<String> = self
            .unmult
            .logs
            .iter()
            .rev()
            .take(14)
            .rev()
            .cloned()
            .collect();
        let progress = self.unmult.progress;
        let defringe = self.unmult.defringe;

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
                        Button::new("pick-images")
                            .label("选择图片…")
                            .disabled(running)
                            .on_click(cx.listener(|this, _, _, cx| this.pick_images(cx))),
                    )
                    .child(
                        div()
                            .text_sm()
                            .text_color(theme.muted_foreground)
                            .child(picked),
                    )
                    .child(div().flex_1())
                    .child(
                        Button::new("pick-out")
                            .label("输出目录…")
                            .disabled(running)
                            .on_click(cx.listener(|this, _, _, cx| this.pick_output_dir(cx))),
                    )
                    .child(
                        div()
                            .max_w(px(360.))
                            .overflow_hidden()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child(self.unmult.out_dir.clone()),
                    ),
            )
            .child(
                h_flex()
                    .gap_2()
                    .items_center()
                    .child(div().text_sm().child("背景:"))
                    .children([Mode::Auto, Mode::Black, Mode::White].map(|mode| {
                        Button::new(format!("mode-{}", mode.key()))
                            .label(mode.label())
                            .small()
                            .selected(self.unmult.mode == mode)
                            .disabled(running)
                            .on_click(cx.listener(move |this, _, _, cx| {
                                this.unmult.mode = mode;
                                cx.notify();
                            }))
                    }))
                    .child(div().w(px(16.)))
                    .child(div().text_sm().child("去边:"))
                    .children([0.0_f32, 0.5, 1.0].map(|strength| {
                        Button::new(format!("defringe-{}", (strength * 10.0) as i32))
                            .label(if strength == 0.0 {
                                "关闭".to_string()
                            } else {
                                format!("{strength:.1}")
                            })
                            .small()
                            .selected((defringe - strength).abs() < f32::EPSILON)
                            .disabled(running)
                            .on_click(cx.listener(move |this, _, _, cx| {
                                this.unmult.defringe = strength;
                                cx.notify();
                            }))
                    })),
            )
            .child(
                h_flex()
                    .gap_5()
                    .items_center()
                    .child(
                        Checkbox::new("rebuild-alpha")
                            .label("重建 Alpha")
                            .checked(self.unmult.rebuild_alpha)
                            .disabled(running)
                            .on_change(cx.listener(|this, checked, _, cx| {
                                this.unmult.rebuild_alpha = *checked;
                                cx.notify();
                            })),
                    )
                    .child(
                        Checkbox::new("no-overwrite")
                            .label("跳过已存在的输出")
                            .checked(self.unmult.no_overwrite)
                            .disabled(running)
                            .on_change(cx.listener(|this, checked, _, cx| {
                                this.unmult.no_overwrite = *checked;
                                cx.notify();
                            })),
                    ),
            )
            .child(
                h_flex()
                    .gap_3()
                    .items_center()
                    .child(
                        Button::new("run")
                            .primary()
                            .label(if running { "处理中…" } else { "开始" })
                            .disabled(running || self.unmult.paths.is_empty())
                            .on_click(cx.listener(|this, _, _, cx| this.run_unmult(cx))),
                    )
                    .child(div().flex_1().child(Progress::new("unmult-progress").value(percent)))
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

    pub(crate) fn pick_images(&mut self, cx: &mut Context<Self>) {
        let (tx, rx) = smol::channel::unbounded();
        std::thread::spawn(move || {
            let files = rfd::FileDialog::new()
                .add_filter("图片", &["png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp"])
                .pick_files();
            let _ = tx.send_blocking(files);
        });
        cx.spawn(async move |this, cx| {
            if let Ok(Some(files)) = rx.recv().await {
                let _ = this.update(cx, |shell, cx| {
                    shell.unmult.paths = files;
                    let count = shell.unmult.paths.len();
                    shell.unmult.push_log(format!("已选择 {count} 张图片"));
                    cx.notify();
                });
            }
        })
        .detach();
    }

    pub(crate) fn pick_output_dir(&mut self, cx: &mut Context<Self>) {
        let (tx, rx) = smol::channel::unbounded();
        std::thread::spawn(move || {
            let dir = rfd::FileDialog::new().pick_folder();
            let _ = tx.send_blocking(dir);
        });
        cx.spawn(async move |this, cx| {
            if let Ok(Some(dir)) = rx.recv().await {
                let _ = this.update(cx, |shell, cx| {
                    shell.unmult.out_dir = dir.display().to_string();
                    cx.notify();
                });
            }
        })
        .detach();
    }

    pub(crate) fn run_unmult(&mut self, cx: &mut Context<Self>) {
        if self.unmult.paths.is_empty() || self.unmult.running {
            return;
        }
        let paths: Vec<String> = self
            .unmult
            .paths
            .iter()
            .map(|path| path.display().to_string())
            .collect();
        let payload = json!({
            "paths": paths,
            "out": self.unmult.out_dir,
            "mode": self.unmult.mode.key(),
            "defringe": self.unmult.defringe,
            "rebuild_alpha": self.unmult.rebuild_alpha,
            "no_overwrite": self.unmult.no_overwrite,
        });
        self.send_job(crate::JobKind::Unmult, "unmult_process", payload);
        self.unmult.running = true;
        self.unmult.progress = (0, paths.len() as u64);
        self.unmult.push_log(format!("开始处理 {} 张图片…", paths.len()));
        cx.notify();
    }
}
