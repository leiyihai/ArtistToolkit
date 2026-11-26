//! 「HDRI 转天空盒」页:HDRI → Blender 烘焙 → 4×3 切图 → 6 面 + bedwars 版,并可在浏览器预览。
//!
//! 对应 Electron 版 `tools/img2box/frontend/view.js`;后端命令 `img2box_process`、
//! `img2box_find_blender`、`img2box_preview`。

use gpui_kit::component::*;
use gpui_kit::*;
use serde_json::json;

use crate::{Shell, theme, widgets::{self, path_box}};

pub struct Img2BoxState {
    pub hdri: String,
    pub blender: String,
    pub out_dir: String,
    pub skybox_dir: String,
    pub stage: String,
    pub running: bool,
    pub logs: Vec<String>,
    pub preview_url: Option<String>,
}

impl Default for Img2BoxState {
    fn default() -> Self {
        let home = std::env::var("USERPROFILE").unwrap_or_default();
        let desktop = std::path::PathBuf::from(&home).join("Desktop");
        let out_dir = if desktop.is_dir() {
            desktop.display().to_string()
        } else {
            home
        };
        // 开发期自动化:ATK_UI_HDRI / ATK_UI_BLENDER / ATK_UI_SKYBOX 预填路径(仅 debug 构建生效)。
        let (hdri, blender) = if cfg!(debug_assertions) {
            (
                std::env::var("ATK_UI_HDRI").unwrap_or_default(),
                std::env::var("ATK_UI_BLENDER").unwrap_or_default(),
            )
        } else {
            (String::new(), String::new())
        };
        Self {
            hdri,
            blender,
            out_dir,
            skybox_dir: if cfg!(debug_assertions) {
                std::env::var("ATK_UI_SKYBOX").unwrap_or_default()
            } else {
                String::new()
            },
            stage: String::new(),
            running: false,
            logs: Vec::new(),
            preview_url: None,
        }
    }
}

impl Img2BoxState {
    pub fn push_log(&mut self, text: impl Into<String>) {
        self.logs.push(text.into());
        if self.logs.len() > 300 {
            self.logs.drain(0..self.logs.len() - 300);
        }
    }
}

impl Shell {
    pub(crate) fn img2box_view(&mut self, cx: &mut Context<Self>) -> impl IntoElement {
        let running = self.img2box.running;
        let logs: Vec<String> = self
            .img2box
            .logs
            .iter()
            .rev()
            .take(14)
            .rev()
            .cloned()
            .collect();
        let hdri = if self.img2box.hdri.is_empty() {
            "未选择 HDRI".to_string()
        } else {
            self.img2box.hdri.clone()
        };
        let blender = if self.img2box.blender.is_empty() {
            "未指定 blender.exe".to_string()
        } else {
            self.img2box.blender.clone()
        };
        let skybox = if self.img2box.skybox_dir.is_empty() {
            "6 张面图(right/left/top/bottom/front/back.png)所在文件夹".to_string()
        } else {
            self.img2box.skybox_dir.clone()
        };
        let out_dir = self.img2box.out_dir.clone();

        v_flex()
            .size_full()
            .min_h_0()
            .gap(px(16.))
            .child(
                widgets::card()
                    .child(widgets::card_title("1 · 输入 HDRI"))
                    .child(
                        widgets::dropzone(
                            "img2box-drop",
                            "将 HDRI 图片拖到此处,或点击选择(单张 PNG)",
                        )
                        .on_click(cx.listener(|this, _, _, cx| this.img2box_pick_hdri(cx))),
                    )
                    .child(
                        h_flex()
                            .mt(px(12.))
                            .gap(px(10.))
                            .items_center()
                            .child(widgets::button(
                                "img2box-pick",
                                "选择图片…",
                                false,
                                cx.listener(|this, _, _, cx| this.img2box_pick_hdri(cx)),
                            ))
                            .child(widgets::button(
                                "img2box-clear",
                                "清空",
                                false,
                                cx.listener(|this, _, _, cx| {
                                    this.img2box.hdri.clear();
                                    cx.notify();
                                }),
                            ))
                            .child(
                                div()
                                    .text_size(px(12.))
                                    .text_color(theme::muted())
                                    .overflow_hidden()
                                    .child(hdri),
                            ),
                    ),
            )
            .child(
                widgets::card()
                    .child(widgets::card_title("2 · 环境"))
                    .child(
                        widgets::field("Blender")
                            .child(
                                h_flex()
                                    .flex_1()
                                    .min_w_0()
                                    .items_center()
                                    .gap(px(10.))
                                    .child(path_box(blender, true))
                                    .child(widgets::button(
                                        "img2box-blender-browse",
                                        "浏览…",
                                        false,
                                        cx.listener(|this, _, _, cx| {
                                            this.img2box_pick_blender(cx)
                                        }),
                                    ))
                                    .child(widgets::button(
                                        "img2box-blender-detect",
                                        "自动探测",
                                        false,
                                        cx.listener(|this, _, _, cx| {
                                            this.img2box_find_blender(cx)
                                        }),
                                    )),
                            ),
                    )
                    .child(
                        div()
                            .mt(px(6.))
                            .pl(px(84.))
                            .text_size(px(11.))
                            .text_color(theme::muted())
                            .child("支持 Blender 3.x / 4.x / 5.x,自动匹配对应版本模板;其他版本可能无法打开模板"),
                    )
                    .child(
                        widgets::field("输出目录").mt(px(12.)).child(
                            h_flex()
                                .flex_1()
                                .min_w_0()
                                .items_center()
                                .gap(px(10.))
                                .child(path_box(out_dir, true))
                                .child(widgets::button(
                                    "img2box-out",
                                    "浏览…",
                                    false,
                                    cx.listener(|this, _, _, cx| this.img2box_pick_out(cx)),
                                )),
                        ),
                    ),
            )
            .child(widgets::runbar().child(widgets::button(
                "img2box-run",
                if running { "烘焙中…" } else { "开始转换" },
                true,
                cx.listener(|this, _, _, cx| this.run_img2box(cx)),
            )))
            .child(
                widgets::card()
                    .child(widgets::card_title("预览天空盒"))
                    .child(
                        widgets::field("面图目录")
                            .child(
                                h_flex()
                                    .flex_1()
                                    .min_w_0()
                                    .items_center()
                                    .gap(px(10.))
                                    .child(path_box(skybox, false))
                                    .child(widgets::button(
                                        "img2box-skybox",
                                        "浏览…",
                                        false,
                                        cx.listener(|this, _, _, cx| {
                                            this.img2box_pick_skybox(cx)
                                        }),
                                    )),
                            ),
                    )
                    .child(
                        h_flex()
                            .mt(px(12.))
                            .pl(px(84.))
                            .gap(px(14.))
                            .items_center()
                            .child(
                                div()
                                    .text_size(px(12.))
                                    .text_color(theme::muted())
                                    .child("在浏览器中打开 3D 天空盒(拖拽旋转视角),无需重新烘焙"),
                            )
                            .child(widgets::button(
                                "img2box-preview",
                                "在浏览器中预览",
                                true,
                                cx.listener(|this, _, _, cx| this.img2box_preview(cx)),
                            )),
                    ),
            )
            .child(
                widgets::card()
                    .child(widgets::card_title("运行日志"))
                    .child(widgets::log_panel(logs)),
            )
    }

    fn img2box_pick(
        &mut self,
        cx: &mut Context<Self>,
        target: PickTarget,
    ) {
        let (tx, rx) = smol::channel::unbounded();
        std::thread::spawn(move || {
            let dialog = rfd::FileDialog::new();
            let picked = match target {
                PickTarget::Hdri => dialog
                    .add_filter("HDRI", &["png", "hdr", "exr", "jpg", "jpeg"])
                    .pick_file(),
                PickTarget::Blender => dialog
                    .add_filter("Blender", &["exe"])
                    .pick_file(),
                PickTarget::Dir => dialog.pick_folder(),
            };
            let _ = tx.send_blocking(picked);
        });
        cx.spawn(async move |this, cx| {
            if let Ok(Some(path)) = rx.recv().await {
                let value = path.display().to_string();
                let _ = this.update(cx, |shell, cx| {
                    match target {
                        PickTarget::Hdri => shell.img2box.hdri = value,
                        PickTarget::Blender => shell.img2box.blender = value,
                        PickTarget::Dir => shell.img2box.skybox_dir = value,
                    }
                    cx.notify();
                });
            }
        })
        .detach();
    }

    pub(crate) fn img2box_pick_hdri(&mut self, cx: &mut Context<Self>) {
        self.img2box_pick(cx, PickTarget::Hdri);
    }

    pub(crate) fn img2box_pick_blender(&mut self, cx: &mut Context<Self>) {
        self.img2box_pick(cx, PickTarget::Blender);
    }

    pub(crate) fn img2box_pick_skybox(&mut self, cx: &mut Context<Self>) {
        self.img2box_pick(cx, PickTarget::Dir);
    }

    pub(crate) fn img2box_pick_out(&mut self, cx: &mut Context<Self>) {
        let (tx, rx) = smol::channel::unbounded();
        std::thread::spawn(move || {
            let dir = rfd::FileDialog::new().pick_folder();
            let _ = tx.send_blocking(dir);
        });
        cx.spawn(async move |this, cx| {
            if let Ok(Some(dir)) = rx.recv().await {
                let _ = this.update(cx, |shell, cx| {
                    shell.img2box.out_dir = dir.display().to_string();
                    cx.notify();
                });
            }
        })
        .detach();
    }

    pub(crate) fn img2box_find_blender(&mut self, cx: &mut Context<Self>) {
        self.query_job(crate::Query::FindBlender, "img2box_find_blender", json!({}));
        self.img2box.push_log("正在探测 Blender…");
        cx.notify();
    }

    pub(crate) fn img2box_preview(&mut self, cx: &mut Context<Self>) {
        self.query_job(
            crate::Query::Preview,
            "img2box_preview",
            json!({ "skybox_dir": self.img2box.skybox_dir }),
        );
        self.img2box.push_log("正在启动预览服务…");
        cx.notify();
    }

    pub(crate) fn run_img2box(&mut self, cx: &mut Context<Self>) {
        if self.img2box.running || self.img2box.hdri.is_empty() || self.img2box.blender.is_empty() {
            return;
        }
        let payload = json!({
            "input": self.img2box.hdri,
            "blender_path": self.img2box.blender,
            "out_dir": self.img2box.out_dir,
        });
        self.send_job(crate::JobKind::Img2Box, "img2box_process", payload);
        self.img2box.running = true;
        self.img2box.stage = "启动中…".to_string();
        self.img2box.push_log("开始烘焙…");
        cx.notify();
    }
}

#[derive(Clone, Copy)]
enum PickTarget {
    Hdri,
    Blender,
    Dir,
}

/// 用系统默认程序打开 URL(仅 Windows 目标)。
pub fn open_url(url: &str) -> bool {
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("cmd")
            .args(["/C", "start", "", url])
            .spawn()
            .is_ok()
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = url;
        false
    }
}

