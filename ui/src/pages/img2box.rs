//! 「HDRI 转天空盒」页:HDRI → Blender 烘焙 → 4×3 切图 → 6 面 + bedwars 版,并可在浏览器预览。
//!
//! 对应 Electron 版 `tools/img2box/frontend/view.js`;后端命令 `img2box_process`、
//! `img2box_find_blender`、`img2box_preview`。

use gpui_kit::component::{button::Button, button::ButtonVariants, progress::Progress, *};
use gpui_kit::*;
use serde_json::json;

use crate::Shell;

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
        let theme = cx.theme().clone();
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
        let stage = self.img2box.stage.clone();
        let preview_url = self.img2box.preview_url.clone();

        v_flex()
            .size_full()
            .min_h_0()
            .gap_3()
            .p_4()
            .child(
                h_flex()
                    .gap_2()
                    .items_center()
                    .child(div().text_sm().child("HDRI:"))
                    .child(
                        Button::new("hdri-pick")
                            .label("选择图片…")
                            .disabled(running)
                            .on_click(cx.listener(|this, _, _, cx| this.img2box_pick_hdri(cx))),
                    )
                    .child(
                        div()
                            .max_w(px(380.))
                            .overflow_hidden()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child(hdri),
                    )
                    .child(div().flex_1())
                    .child(
                        Button::new("hdri-out")
                            .label("输出目录…")
                            .disabled(running)
                            .on_click(cx.listener(|this, _, _, cx| this.img2box_pick_out(cx))),
                    )
                    .child(
                        div()
                            .max_w(px(340.))
                            .overflow_hidden()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child(self.img2box.out_dir.clone()),
                    ),
            )
            .child(
                h_flex()
                    .gap_2()
                    .items_center()
                    .child(div().text_sm().child("Blender:"))
                    .child(
                        Button::new("blender-detect")
                            .label("自动探测")
                            .small()
                            .disabled(running)
                            .on_click(cx.listener(|this, _, _, cx| this.img2box_find_blender(cx))),
                    )
                    .child(
                        Button::new("blender-pick")
                            .label("浏览…")
                            .small()
                            .disabled(running)
                            .on_click(cx.listener(|this, _, _, cx| this.img2box_pick_blender(cx))),
                    )
                    .child(
                        div()
                            .max_w(px(520.))
                            .overflow_hidden()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child(blender),
                    ),
            )
            .child(
                div()
                    .text_xs()
                    .text_color(theme.muted_foreground)
                    .child("支持 Blender 3.x / 4.x / 5.x,自动匹配对应版本模板;烘焙在 Blender 后台进程中完成。"),
            )
            .child(
                h_flex()
                    .gap_3()
                    .items_center()
                    .child(
                        Button::new("img2box-run")
                            .primary()
                            .label(if running { "烘焙中…" } else { "开始转换" })
                            .disabled(
                                running
                                    || self.img2box.hdri.is_empty()
                                    || self.img2box.blender.is_empty(),
                            )
                            .on_click(cx.listener(|this, _, _, cx| this.run_img2box(cx))),
                    )
                    .child(
                        div()
                            .flex_1()
                            .child(Progress::new("img2box-progress").loading(running).value(0.0)),
                    )
                    .child(
                        div()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child(stage),
                    ),
            )
            .child(
                h_flex()
                    .gap_2()
                    .items_center()
                    .child(
                        Button::new("skybox-pick")
                            .label("选择面图目录…")
                            .small()
                            .on_click(cx.listener(|this, _, _, cx| this.img2box_pick_skybox(cx))),
                    )
                    .child(
                        div()
                            .max_w(px(420.))
                            .overflow_hidden()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child(if self.img2box.skybox_dir.is_empty() {
                                "预览:未选择面图目录(right/left/top/bottom/front/back.png 所在)".to_string()
                            } else {
                                self.img2box.skybox_dir.clone()
                            }),
                    )
                    .child(
                        Button::new("skybox-open")
                            .label("在浏览器中预览")
                            .small()
                            .disabled(self.img2box.skybox_dir.is_empty())
                            .on_click(cx.listener(|this, _, _, cx| this.img2box_preview(cx))),
                    )
                    .child(
                        div()
                            .text_xs()
                            .text_color(theme.muted_foreground)
                            .child(preview_url.unwrap_or_default()),
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

