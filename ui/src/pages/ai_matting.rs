//! 「AI 抠图」页:图片一键去背景,输出透明 PNG。
//!
//! 对应 Electron 版 `tools/ai_matting/frontend/view.js`;后端命令 `matting_process`。

use std::path::PathBuf;

use gpui_kit::component::*;
use gpui_kit::prelude::FluentBuilder as _;
use gpui_kit::*;
use serde_json::json;

use crate::thumbs::ThumbCache;
use crate::{Shell, theme, widgets};

pub struct AiMattingState {
    pub paths: Vec<PathBuf>,
    pub out_dir: String,
    pub running: bool,
    pub progress: (u64, u64),
    pub logs: Vec<String>,
    pub thumbs: ThumbCache,
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
        let thumbs = ThumbCache::new(&paths);
        Self {
            thumbs,
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

}

impl Shell {
    pub(crate) fn matting_view(&mut self, cx: &mut Context<Self>) -> impl IntoElement {
        let running = self.matting.running;
        let picked = if self.matting.paths.is_empty() {
            "未选择图片".to_string()
        } else {
            format!("已选 {} 张", self.matting.paths.len())
        };
        let total = self.matting.paths.len();
        let thumbs = widgets::thumb_grid(&self.matting.thumbs, &self.matting.paths).into_any_element();
        let logs: Vec<String> = self
            .matting
            .logs
            .iter()
            .rev()
            .take(16)
            .rev()
            .cloned()
            .collect();
        let out_dir = self.matting.out_dir.clone();

        v_flex()
            .size_full()
            .min_h_0()
            .gap(px(16.))
            .child(
                widgets::card()
                    .child(widgets::card_title("1 · 添加图片"))
                    .child(
                        widgets::dropzone(
                            "matting-drop",
                            "将图片拖到此处,或点击选择(PNG / JPG / WebP,可多张)",
                        )
                        .on_click(cx.listener(|this, _, _, cx| this.matting_pick_images(cx))),
                    )
                    .child(
                        h_flex()
                            .mt(px(12.))
                            .gap(px(10.))
                            .items_center()
                            .child(widgets::button(
                                "matting-pick",
                                "选择图片…",
                                false,
                                cx.listener(|this, _, _, cx| this.matting_pick_images(cx)),
                            ))
                            .child(widgets::button(
                                "matting-clear",
                                "清空",
                                false,
                                cx.listener(|this, _, _, cx| {
                                    this.matting.paths.clear();
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
                    .child(widgets::card_title("2 · 输出设置"))
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
                                "matting-out",
                                "浏览…",
                                false,
                                cx.listener(|this, _, _, cx| this.matting_pick_output_dir(cx)),
                            )),
                    ),
            )
            .child(widgets::runbar().child(widgets::button(
                "matting-run",
                if running { "处理中…" } else { "开始抠图" },
                true,
                cx.listener(|this, _, _, cx| this.run_matting(cx)),
            )))
            .child(
                widgets::card()
                    .child(widgets::card_title("运行日志"))
                    .child(widgets::log_panel(logs)),
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
                    shell.matting.thumbs.ensure(&shell.matting.paths);
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
