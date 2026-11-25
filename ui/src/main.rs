//! ArtistToolkit 的 Rust/GPUI 前端(gpui-kit)。
//!
//! 界面外壳用 gpui-kit 的 Sidebar/Button/Label 等组件;功能通过 stdio JSON 复用现有
//! Python 后端(`backend.py` 或打包后的 `ArtistToolkit-backend.exe`),因此抠图模型、
//! PIL 与已移植的 Rust 内核都不需要重写。

mod backend;
mod pages;

use gpui_kit::assets::Assets;
use gpui_kit::component::{
    sidebar::{Sidebar, SidebarFooter, SidebarGroup, SidebarHeader, SidebarMenu, SidebarMenuItem},
    *,
};
use gpui_kit::*;

use backend::Backend;
use pages::unmult::UnmultState;

/// 左侧页签,顺序与 Electron 版 `app/renderer/features.js` 一致。
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Tab {
    IconExport,
    AiMatting,
    ImageResize,
    Unmult,
    Img2Box,
}

impl Tab {
    pub const ALL: [Tab; 5] = [
        Tab::IconExport,
        Tab::AiMatting,
        Tab::ImageResize,
        Tab::Unmult,
        Tab::Img2Box,
    ];

    pub fn title(self) -> &'static str {
        match self {
            Tab::IconExport => "图标批处理",
            Tab::AiMatting => "AI 抠图",
            Tab::ImageResize => "批量缩放",
            Tab::Unmult => "去底",
            Tab::Img2Box => "HDRI 转天空盒",
        }
    }

    pub fn hint(self) -> &'static str {
        match self {
            Tab::IconExport => "抠图 → 拆图标 → 按形状/尺寸裁切输出。",
            Tab::AiMatting => "图片一键去背景,输出透明 PNG。",
            Tab::ImageResize => "递归扫描图片,精确缩放到指定尺寸,保持目录结构。",
            Tab::Unmult => "去黑底/去白底/自动判断,反预乘恢复直通色。",
            Tab::Img2Box => "HDRI → Blender 烘焙 → 4×3 切图 → 6 个天空盒面。",
        }
    }

    fn icon(self) -> IconName {
        match self {
            Tab::IconExport => IconName::GalleryVerticalEnd,
            Tab::AiMatting => IconName::Bot,
            Tab::ImageResize => IconName::Maximize,
            Tab::Unmult => IconName::Frame,
            Tab::Img2Box => IconName::Globe,
        }
    }
}

pub struct Shell {
    tab: Tab,
    backend: Backend,
    pub unmult: UnmultState,
    ping_id: Option<u64>,
    /// 后端最近一次状态提示(侧边栏底部)。
    pub status: String,
}

impl Shell {
    fn new(cx: &mut Context<Self>) -> Self {
        let root = backend::repo_root();
        let (backend, rx) = match Backend::spawn(&root) {
            Ok(pair) => pair,
            Err(error) => panic!("无法启动 Python 后端({}):{error}", root.display()),
        };
        let mut shell = Self {
            tab: Tab::Unmult,
            backend,
            unmult: UnmultState::default(),
            ping_id: None,
            status: "后端连接中…".to_string(),
        };
        shell.ping_id = Some(shell.backend.request("ping", serde_json::json!({})));
        cx.spawn(async move |this, cx| {
            while let Ok(line) = rx.recv().await {
                let alive = this.update(cx, |shell, cx| {
                    shell.on_line(&line);
                    cx.notify();
                });
                if alive.is_err() {
                    break;
                }
            }
        })
        .detach();
        // 开发期自动化:ATK_UI_IMAGES 预填图片 + ATK_UI_AUTORUN 直接开跑,便于截图验证。
        if cfg!(debug_assertions) && std::env::var_os("ATK_UI_AUTORUN").is_some() {
            cx.spawn(async move |this, cx| {
                smol::Timer::after(std::time::Duration::from_millis(900)).await;
                let _ = this.update(cx, |shell, cx| shell.run_unmult(cx));
            })
            .detach();
        }
        shell
    }

    /// 把后端输出的每一行转成界面状态。
    fn on_line(&mut self, line: &str) {
        let Ok(msg) = serde_json::from_str::<serde_json::Value>(line) else {
            if !line.trim().is_empty() {
                self.unmult.push_log(format!("[backend] {line}"));
            }
            return;
        };
        let id = msg.get("id").and_then(|v| v.as_u64());
        match msg.get("event").and_then(|v| v.as_str()) {
            Some("log") => {
                let text = msg.get("message").and_then(|v| v.as_str()).unwrap_or("");
                if id == self.unmult.job_id {
                    self.unmult.push_log(text);
                }
            }
            Some("progress") => {
                let done = msg.get("done").and_then(|v| v.as_u64()).unwrap_or(0);
                let total = msg.get("total").and_then(|v| v.as_u64()).unwrap_or(0);
                if id == self.unmult.job_id {
                    self.unmult.progress = (done, total);
                }
            }
            Some("stderr") => {
                let text = msg.get("message").and_then(|v| v.as_str()).unwrap_or("");
                if !text.trim().is_empty() {
                    self.unmult.push_log(format!("[stderr] {text}"));
                }
            }
            Some(_) => {}
            None => {
                let ok = msg.get("ok").and_then(|v| v.as_bool()).unwrap_or(false);
                if id == self.ping_id {
                    self.status = if ok {
                        "后端已连接".to_string()
                    } else {
                        "后端无响应".to_string()
                    };
                } else if id.is_some() && id == self.unmult.job_id {
                    self.unmult.running = false;
                    if ok {
                        let result = msg.get("result").cloned().unwrap_or_default();
                        self.unmult.push_log(format!("完成:{result}"));
                        self.status = "处理完成".into();
                    } else {
                        let error = msg.get("error").and_then(|v| v.as_str()).unwrap_or("未知错误");
                        self.unmult.push_log(format!("失败:{error}"));
                        self.status = format!("失败:{error}");
                    }
                }
            }
        }
    }

    fn send(&mut self, cmd: &str, extra: serde_json::Value) -> u64 {
        self.backend.request(cmd, extra)
    }

    fn sidebar(&self, cx: &mut Context<Self>) -> Sidebar<SidebarGroup<SidebarMenu>> {
        let items: Vec<SidebarMenuItem> = Tab::ALL
            .iter()
            .map(|tab| {
                let tab = *tab;
                SidebarMenuItem::new(tab.title())
                    .icon(tab.icon())
                    .active(self.tab == tab)
                    .on_click(cx.listener(move |this, _, _, cx| {
                        this.tab = tab;
                        cx.notify();
                    }))
            })
            .collect();
        Sidebar::new("tabs")
            .w(px(220.))
            .header(
                SidebarHeader::new().child(
                    v_flex()
                        .gap_1()
                        .child(div().font_bold().child("Artist Toolkit"))
                        .child(div().text_xs().child("Rust · GPUI")),
                ),
            )
            .child(SidebarGroup::new("功能").child(SidebarMenu::new().children(items)))
            .footer(SidebarFooter::new().child(
                div()
                    .text_xs()
                    .text_color(cx.theme().muted_foreground)
                    .child(self.status.clone()),
            ))
    }
}

impl Render for Shell {
    fn render(&mut self, _: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        let body = match self.tab {
            Tab::Unmult => self.unmult_view(cx).into_any_element(),
            other => placeholder(other, cx).into_any_element(),
        };
        h_flex()
            .size_full()
            .bg(cx.theme().background)
            .text_color(cx.theme().foreground)
            .child(self.sidebar(cx))
            .child(
                v_flex()
                    .flex_1()
                    .min_w_0()
                    .h_full()
                    .child(
                        h_flex()
                            .items_center()
                            .gap_2()
                            .px_4()
                            .py_3()
                            .border_b_1()
                            .border_color(cx.theme().border)
                            .child(div().font_bold().child(self.tab.title()))
                            .child(
                                div()
                                    .text_sm()
                                    .text_color(cx.theme().muted_foreground)
                                    .child(self.tab.hint()),
                            ),
                    )
                    .child(div().flex_1().min_h_0().child(body)),
            )
    }
}

fn placeholder(tab: Tab, cx: &mut Context<Shell>) -> impl IntoElement {
    v_flex()
        .p_6()
        .gap_3()
        .items_start()
        .child(div().text_lg().font_bold().child(tab.title()))
        .child(
            div()
                .text_color(cx.theme().muted_foreground)
                .child("这一页还没搬到 GPUI。当前版本先打通「去底」页(界面 + 后端 + Rust 内核)。"),
        )
        .child(
            div()
                .text_sm()
                .text_color(cx.theme().muted_foreground)
                .child("Electron 版仍可用:start.bat;逐页移植进度见 rust/PORT_MAP.md。"),
        )
}

fn main() {
    let app = gpui_kit::application().with_assets(Assets);
    app.run(move |cx| {
        gpui_kit::init(cx);

        let options = WindowOptions {
            window_bounds: Some(WindowBounds::centered(None, size(px(1100.), px(720.)), cx)),
            ..Default::default()
        };
        gpui_kit::open_window(options, cx, |_, cx| cx.new(Shell::new))
            .expect("failed to open window");
    });
}
