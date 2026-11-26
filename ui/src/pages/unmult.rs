//! 「去底」页:选图 / 模式 / 去边 → 调后端 unmult_process → 日志与进度。
//!
//! 对应 Electron 版 `tools/unmult/frontend/view.js`;计算本身在 Python 侧,
//! 像素内核已是 Rust(`rust/unmult-rs`)。

use std::path::PathBuf;

use gpui_kit::component::*;
use gpui_kit::prelude::FluentBuilder as _;
use gpui_kit::*;
use serde_json::json;

use gpui_kit::component::slider::{Slider, SliderState};

use crate::thumbs::ThumbCache;
use crate::{Shell, theme, widgets};

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
    /// 边缘清理强度 0–1(与原版 Defringe 滑杆一致)。
    pub defringe: Entity<SliderState>,
    pub rebuild_alpha: bool,
    pub no_overwrite: bool,
    pub running: bool,
    pub progress: (u64, u64),
    pub logs: Vec<String>,
    pub thumbs: ThumbCache,
}

impl UnmultState {
    pub fn new(_window: &mut Window, cx: &mut Context<crate::Shell>) -> Self {
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
        let defringe = cx.new(|_| {
            SliderState::new()
                .min(0.0)
                .max(1.0)
                .step(0.05)
                .default_value(0.0)
        });
        Self {
            thumbs: ThumbCache::new(&paths),
            paths,
            out_dir,
            mode: Mode::Auto,
            defringe,
            rebuild_alpha: false,
            no_overwrite: false,
            running: false,
            progress: (0, 0),
            logs: Vec::new(),
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

}

impl Shell {
    pub(crate) fn unmult_view(&mut self, cx: &mut Context<Self>) -> impl IntoElement {
        let running = self.unmult.running;
        let picked = if self.unmult.paths.is_empty() {
            "未选择图片".to_string()
        } else {
            format!("已选 {} 张", self.unmult.paths.len())
        };
        let total = self.unmult.paths.len();
        let shell = cx.entity();
        let thumbs = widgets::thumb_grid(
            &self.unmult.thumbs,
            &self.unmult.paths,
            move |index, _event, _window, cx| {
                shell.update(cx, |this, cx| {
                    if index < this.unmult.paths.len() {
                        this.unmult.paths.remove(index);
                        cx.notify();
                    }
                });
            },
        )
        .into_any_element();
        let logs: Vec<String> = self
            .unmult
            .logs
            .iter()
            .rev()
            .take(16)
            .rev()
            .cloned()
            .collect();
        let defringe_value = self.unmult.defringe.read(cx).value().start();
        let defringe_label = if defringe_value < 0.005 {
            "0(关闭)".to_string()
        } else {
            format!("{defringe_value:.2}")
        };
        let mode = self.unmult.mode;
        let rebuild = self.unmult.rebuild_alpha;
        let no_overwrite = self.unmult.no_overwrite;
        let out_dir = self.unmult.out_dir.clone();

        let mut mode_seg = widgets::seg_container();
        for (index, item) in [Mode::Auto, Mode::Black, Mode::White].into_iter().enumerate() {
            mode_seg = mode_seg.child(widgets::seg_item(
                ("unmult-mode", index),
                item.label(),
                mode == item,
                !running,
                cx.listener(move |this, _, _, cx| {
                    this.unmult.mode = item;
                    cx.notify();
                }),
            ));
        }

        v_flex()
            .size_full()
            .min_h_0()
            .gap(px(16.))
            .id("unmult-page")
            .on_drop(cx.listener(|this, paths: &ExternalPaths, _, cx| {
                this.accept_drop(crate::Tab::Unmult, paths.0.to_vec(), cx)
            }))
            .child(
                widgets::card()
                    .child(widgets::card_title("1 · 添加图片"))
                    .child(
                        widgets::dropzone(
                            "unmult-drop",
                            "将图片拖到此处,或点击选择(PNG / JPG / TIFF / WebP,可多张)",
                            self.drag_over,
                        )
                        .on_click(cx.listener(|this, _, _, cx| this.pick_images(cx)))
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
                                "unmult-pick",
                                "选择图片…",
                                false,
                                cx.listener(|this, _, _, cx| this.pick_images(cx)),
                            ))
                            .child(widgets::button(
                                "unmult-clear",
                                "清空",
                                false,
                                cx.listener(|this, _, _, cx| {
                                    this.unmult.paths.clear();
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
                    .child(widgets::card_title("2 · 处理选项"))
                    .child(widgets::field("背景模式").child(mode_seg))
                    .child(
                        widgets::field("边缘清理")
                            .mt(px(12.))
                            .child(
                                div()
                                    .flex_1()
                                    .min_w_0()
                                    .child(Slider::new(&self.unmult.defringe).horizontal().disabled(running)),
                            )
                            .child(
                                div()
                                    .w(px(64.))
                                    .flex_none()
                                    .text_right()
                                    .text_size(px(12.))
                                    .text_color(theme::muted())
                                    .child(defringe_label),
                            ),
                    )
                    .child(
                        h_flex()
                            .mt(px(12.))
                            .pl(px(84.))
                            .gap(px(10.))
                            .child(widgets::check_chip(
                                "unmult-rebuild",
                                "忽略输入自带 Alpha,重新计算",
                                rebuild,
                                !running,
                                cx.listener(|this, _, _, cx| {
                                    this.unmult.rebuild_alpha = !this.unmult.rebuild_alpha;
                                    cx.notify();
                                }),
                            ))
                            .child(widgets::check_chip(
                                "unmult-skip",
                                "输出已存在时跳过",
                                no_overwrite,
                                !running,
                                cx.listener(|this, _, _, cx| {
                                    this.unmult.no_overwrite = !this.unmult.no_overwrite;
                                    cx.notify();
                                }),
                            )),
                    ),
            )
            .child(
                widgets::card()
                    .child(widgets::card_title("3 · 输出路径"))
                    .child(
                        widgets::field("输出路径")
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
                                "unmult-out",
                                "浏览…",
                                false,
                                cx.listener(|this, _, _, cx| this.pick_output_dir(cx)),
                            )),
                    ),
            )
            .child(widgets::runbar().child(widgets::button(
                "unmult-run",
                if running { "处理中…" } else { "开始处理" },
                true,
                cx.listener(|this, _, _, cx| this.run_unmult(cx)),
            )))            .child(
                widgets::card()
                    .child(widgets::card_title("运行日志"))
                    .child(widgets::log_panel(logs)),
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
                    shell.unmult.thumbs.ensure(&shell.unmult.paths);
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
            "defringe": self.unmult.defringe.read(cx).value().start(),
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
