#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! ArtistToolkit 的 Rust/GPUI 前端(gpui-kit)。
//!
//! 界面外壳用 gpui-kit 的 Sidebar/Button/Label 等组件;功能通过 stdio JSON 复用现有
//! Python 后端(`backend.py` 或打包后的 `ArtistToolkit-backend.exe`),因此抠图模型、
//! PIL 与已移植的 Rust 内核都不需要重写。

mod backend;
mod pages;
mod theme;
mod thumbs;
mod widgets;

use gpui_kit::assets::Assets;
use gpui_kit::component::slider::SliderEvent;
use gpui_kit::component::*;
use gpui_kit::prelude::FluentBuilder as _;
use gpui_kit::*;

use std::path::{Path, PathBuf};

use backend::Backend;
use pages::ai_matting::AiMattingState;
use pages::icon_export::IconExportState;
use pages::img2box::Img2BoxState;
use pages::image_resize::ImageResizeState;
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
    /// 顺序与 Electron 版 pp/renderer/features.js 一致。
    pub const ALL: [Tab; 5] = [
        Tab::AiMatting,
        Tab::Unmult,
        Tab::IconExport,
        Tab::ImageResize,
        Tab::Img2Box,
    ];

    pub fn title(self) -> &'static str {
        match self {
            Tab::IconExport => "图集拆分",
            Tab::AiMatting => "智能抠图",
            Tab::ImageResize => "快捷尺寸",
            Tab::Unmult => "特效抠图",
            Tab::Img2Box => "天空盒烘焙",
        }
    }

    pub fn hint(self) -> &'static str {
        match self {
            Tab::IconExport => "选择旧版拆分或 AI 图集命名流程",
            Tab::AiMatting => "拖入图片 → AI 去除背景 → 输出透明背景 PNG(保留原尺寸)",
            Tab::ImageResize => "递归扫描文件夹 → 精确缩放到目标尺寸 → 保持目录结构输出",
            Tab::Unmult => "去掉黑底 / 白底,输出带真实 Alpha 的透明 PNG(火焰、烟雾、粒子、光效素材)",
            Tab::Img2Box => "HDRI 全景图 → Blender 烘焙 → 4×3 网格切图 → 6 个天空盒面(含 bedwars 版)",
        }
    }

}

/// 一次性查询(非长任务),走同一套 stdio 协议。
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Query {
    FindBlender,
    Preview,
}

/// 当前在跑的任务属于哪一页,用于把后端的 log/progress 送回正确的页。
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum JobKind {
    Unmult,
    IconExport,
    Matting,
    Resize,
    Img2Box,
}

pub struct Shell {
    tab: Tab,
    backend: Backend,
    pub unmult: UnmultState,
    pub icon: IconExportState,
    pub matting: AiMattingState,
    pub resize: ImageResizeState,
    pub img2box: Img2BoxState,
    query: Option<(Query, u64)>,
    _slider_subs: Vec<Subscription>,
    job: Option<(JobKind, u64)>,
    ping_id: Option<u64>,
    /// 后端最近一次状态提示(侧边栏底部)。
    pub status: String,
}

impl Shell {
    fn new(window: &mut Window, cx: &mut Context<Self>) -> Self {
        let root = backend::app_root();
        let (backend, rx) = match Backend::spawn(&root) {
            Ok(pair) => pair,
            Err(error) => panic!("无法启动 Python 后端({}):{error}", root.display()),
        };
        let mut shell = Self {
            tab: if cfg!(debug_assertions) {
                match std::env::var("ATK_UI_TAB").ok().as_deref() {
                    Some("icon") => Tab::IconExport,
                    Some("matting") => Tab::AiMatting,
                    Some("resize") => Tab::ImageResize,
                    Some("img2box") => Tab::Img2Box,
                    Some("unmult") => Tab::Unmult,
                    _ => Tab::Unmult,
                }
            } else {
                Tab::AiMatting
            },
            backend,
            unmult: UnmultState::new(window, cx),
            icon: IconExportState::new(window, cx),
            matting: AiMattingState::default(),
            resize: ImageResizeState::new(window, cx),
            img2box: Img2BoxState::default(),
            query: None,
            _slider_subs: Vec::new(),
            job: None,
            ping_id: None,
            status: "后端连接中…".to_string(),
        };
        shell.ping_id = Some(shell.backend.request("ping", serde_json::json!({})));
        // 滑杆自身不驱动重绘:订阅变更后通知界面刷新。
        shell._slider_subs = vec![
            cx.subscribe_in(&shell.icon.corner, window, |_, _, _: &SliderEvent, _, cx| {
                cx.notify()
            }),
            cx.subscribe_in(&shell.unmult.defringe, window, |_, _, _: &SliderEvent, _, cx| {
                cx.notify()
            }),
        ];
        // 开发期自动化:ATK_UI_DROP="a.png;b.png" 走与拖放完全相同的处理函数(仅 debug 构建生效)。
        if cfg!(debug_assertions)
            && let Ok(list) = std::env::var("ATK_UI_DROP")
        {
            let paths: Vec<PathBuf> = list
                .split(';')
                .filter(|part| !part.is_empty())
                .map(PathBuf::from)
                .collect();
            let tab = shell.tab;
            shell.accept_drop(tab, paths, cx);
        }
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
        // 开发期自动化:ATK_UI_IMAGES 预填图片 + ATK_UI_TAB 选页 + ATK_UI_AUTORUN 直接开跑。
        if cfg!(debug_assertions) && std::env::var_os("ATK_UI_AUTORUN").is_some() {
            cx.spawn(async move |this, cx| {
                smol::Timer::after(std::time::Duration::from_millis(900)).await;
                let action = std::env::var("ATK_UI_AUTORUN").unwrap_or_default();
                let _ = this.update(cx, |shell, cx| match action.as_str() {
                    "detect" if shell.tab == Tab::Img2Box => shell.img2box_find_blender(cx),
                    "preview" if shell.tab == Tab::Img2Box => shell.img2box_preview(cx),
                    _ => match shell.tab {
                        Tab::IconExport => shell.run_icon_export(cx),
                        Tab::Unmult => shell.run_unmult(cx),
                        Tab::AiMatting => shell.run_matting(cx),
                        Tab::ImageResize => shell.run_resize(cx),
                        Tab::Img2Box => shell.run_img2box(cx),
                    },
                });
            })
            .detach();
        }
        shell
    }

    /// 接受一次文件拖放(来自 `on_drop`,或开发期 `ATK_UI_DROP`)。
    pub(crate) fn accept_drop(&mut self, tab: Tab, paths: Vec<PathBuf>, cx: &mut Context<Self>) {
        let images: Vec<PathBuf> = paths.iter().filter(|path| is_image(path)).cloned().collect();
        match tab {
            Tab::ImageResize => {
                let dir = paths
                    .iter()
                    .find(|path| path.is_dir())
                    .cloned()
                    .or_else(|| {
                        images
                            .first()
                            .and_then(|path| path.parent())
                            .map(Path::to_path_buf)
                    });
                match dir {
                    Some(dir) => {
                        self.resize.input_dir = dir.display().to_string();
                        let text = format!("拖入目录:{}", self.resize.input_dir);
                        self.resize.push_log(text);
                    }
                    None => self.resize.push_log("拖入的内容里没有文件夹。"),
                }
            }
            Tab::Img2Box => match images.first() {
                Some(first) => {
                    self.img2box.hdri = first.display().to_string();
                    let text = format!("拖入 HDRI:{}", first.display());
                    self.img2box.push_log(text);
                }
                None => self.img2box.push_log("拖入的内容里没有图片。"),
            },
            Tab::Unmult => {
                let text = append_drop_images(&mut self.unmult.paths, images, "PNG / JPG / TIFF / WebP");
                self.unmult.thumbs.ensure(&self.unmult.paths);
                self.unmult.push_log(text);
            }
            Tab::IconExport => {
                let text = append_drop_images(&mut self.icon.paths, images, "PNG / JPG / WebP");
                self.icon.thumbs.ensure(&self.icon.paths);
                self.icon.push_log(text);
            }
            Tab::AiMatting => {
                let text = append_drop_images(&mut self.matting.paths, images, "PNG / JPG / WebP");
                self.matting.thumbs.ensure(&self.matting.paths);
                self.matting.push_log(text);
            }
        }
        cx.notify();
    }

    fn job_log(&mut self, kind: JobKind, text: impl Into<String>) {
        match kind {
            JobKind::Unmult => self.unmult.push_log(text),
            JobKind::IconExport => self.icon.push_log(text),
            JobKind::Matting => self.matting.push_log(text),
            JobKind::Resize => self.resize.push_log(text),
            JobKind::Img2Box => self.img2box.push_log(text),
        }
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
        let job = self.job;
        match msg.get("event").and_then(|v| v.as_str()) {
            Some("log") => {
                let text = msg.get("message").and_then(|v| v.as_str()).unwrap_or("");
                if let Some((kind, job_id)) = job
                    && Some(job_id) == id
                {
                    self.job_log(kind, text);
                }
            }
            Some("progress") => {
                let done = msg.get("done").and_then(|v| v.as_u64()).unwrap_or(0);
                let total = msg.get("total").and_then(|v| v.as_u64()).unwrap_or(0);
                if let Some((kind, job_id)) = job
                    && Some(job_id) == id
                {
                    match kind {
                        JobKind::Unmult => self.unmult.progress = (done, total),
                        JobKind::Matting => self.matting.progress = (done, total),
                        JobKind::Resize => self.resize.progress = (done, total),
                        JobKind::Img2Box => {
                            if let Some(stage) = msg.get("message").and_then(|v| v.as_str()) {
                                self.img2box.stage = stage.to_string();
                            }
                        }
                        JobKind::IconExport => {}
                    }
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
                } else if let Some((query, query_id)) = self.query
                    && Some(query_id) == id
                {
                    self.query = None;
                    let text = msg
                        .get("result")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string();
                    self.on_query_result(query, text, ok);
                } else if let Some((kind, job_id)) = job
                    && Some(job_id) == id
                {
                    self.run_finished(kind, &msg, ok);
                }
            }
        }
    }

    fn on_query_result(&mut self, query: Query, text: String, ok: bool) {
        match query {
            Query::FindBlender => {
                if !ok || text.is_empty() {
                    self.img2box.push_log("未探测到 Blender,请手动浏览选择 blender.exe");
                } else {
                    self.img2box.push_log(format!("已探测到 Blender:{text}"));
                    self.img2box.blender = text;
                }
            }
            Query::Preview => {
                if !ok || text.is_empty() {
                    self.img2box.push_log("预览服务启动失败。");
                } else {
                    let suppress = cfg!(debug_assertions) && std::env::var_os("ATK_UI_NO_BROWSER").is_some();
                    let opened = !suppress && pages::img2box::open_url(&text);
                    self.img2box.push_log(if opened {
                        format!("已在浏览器打开:{text}")
                    } else {
                        format!("预览地址:{text}")
                    });
                    self.img2box.preview_url = Some(text);
                }
            }
        }
    }

    pub(crate) fn query_job(&mut self, query: Query, cmd: &str, extra: serde_json::Value) -> u64 {
        let id = self.backend.request(cmd, extra);
        self.query = Some((query, id));
        id
    }
    fn set_running(&mut self, kind: JobKind, running: bool) {
        match kind {
            JobKind::Unmult => self.unmult.running = running,
            JobKind::IconExport => self.icon.running = running,
            JobKind::Matting => self.matting.running = running,
            JobKind::Resize => self.resize.running = running,
            JobKind::Img2Box => self.img2box.running = running,
        }
    }

    fn run_finished(&mut self, kind: JobKind, msg: &serde_json::Value, ok: bool) {
        let result = msg.get("result").cloned().unwrap_or_default();
        let error = msg
            .get("error")
            .and_then(|v| v.as_str())
            .unwrap_or("未知错误")
            .to_string();
        self.set_running(kind, false);
        if ok {
            self.job_log(kind, format!("完成:{result}"));
            self.status = "处理完成".to_string();
        } else {
            self.job_log(kind, format!("失败:{error}"));
            self.status = format!("失败:{error}");
        }
        self.job = None;
    }

    pub(crate) fn send_job(
        &mut self,
        kind: JobKind,
        cmd: &str,
        extra: serde_json::Value,
    ) -> u64 {
        let id = self.backend.request(cmd, extra);
        self.job = Some((kind, id));
        id
    }

    /// 侧边栏:白底 208px、品牌行 + 页签(`.nav-btn`,选中为珊瑚橙浅底)。
    fn sidebar(&self, cx: &mut Context<Self>) -> impl IntoElement {
        v_flex()
            .w(px(theme::SIDEBAR_WIDTH))
            .h_full()
            .flex_none()
            .bg(theme::panel())
            .border_r_1()
            .border_color(theme::border())
            .child(
                h_flex()
                    .items_center()
                    .gap(px(10.))
                    .px(px(16.))
                    .pt(px(18.))
                    .pb(px(14.))
                    .border_b_1()
                    .border_color(theme::border())
                    .child(
                        div()
                            .size(px(22.))
                            .flex_none()
                            .rounded_full()
                            .bg(linear_gradient(
                                135.0,
                                linear_color_stop(theme::accent(), 0.0),
                                linear_color_stop(rgb(0xf0b48f), 1.0),
                            )),
                    )
                    .child(
                        div()
                            .text_size(px(14.))
                            .font_weight(FontWeight::SEMIBOLD)
                            .child("Artist Toolkit"),
                    ),
            )
            .child(
                v_flex()
                    .flex_1()
                    .gap(px(2.))
                    .px(px(8.))
                    .py(px(10.))
                    .children({
                        let mut items = Vec::new();
                        for tab in Tab::ALL {
                            items.push(self.nav_item(tab, cx));
                        }
                        items
                    }),
            )
            .child(
                div()
                    .px(px(16.))
                    .py(px(10.))
                    .text_size(px(11.))
                    .text_color(theme::muted())
                    .child(self.status.clone()),
            )
    }

    /// 单个页签按钮(`.nav-btn`):左对齐文本、10px 圆角、悬停浅底、选中珊瑚橙浅底。
    fn nav_item(&self, tab: Tab, cx: &mut Context<Self>) -> AnyElement {
        let active = self.tab == tab;
        div()
            .id(("nav", tab as usize))
            .w_full()
            .px(px(14.))
            .py(px(10.))
            .rounded(px(theme::RADIUS))
            .text_size(px(13.))
            .text_color(if active { theme::text() } else { theme::muted() })
            .when(active, |this| {
                this.bg(theme::accent_dim())
                    .font_weight(FontWeight::SEMIBOLD)
            })
            .when(!active, |this| this.hover(|this| this.bg(theme::panel_2())))
            .cursor_pointer()
            .child(tab.title())
            .on_click(cx.listener(move |this, _, _, cx| {
                this.tab = tab;
                cx.notify();
            }))
            .into_any_element()
    }
}

impl Render for Shell {
    fn render(&mut self, _: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        let body = match self.tab {
            Tab::Unmult => self.unmult_view(cx).into_any_element(),
            Tab::IconExport => self.icon_view(cx).into_any_element(),
            Tab::AiMatting => self.matting_view(cx).into_any_element(),
            Tab::ImageResize => self.resize_view(cx).into_any_element(),
            Tab::Img2Box => self.img2box_view(cx).into_any_element(),
        };
        h_flex()
            .size_full()
            .bg(theme::bg())
            .text_color(theme::text())
            .child(self.sidebar(cx))
            .child(
                v_flex()
                    .id("content-scroll")
                    .flex_1()
                    .min_w_0()
                    .min_h_0()
                    .h_full()
                    .overflow_y_scroll()
                    .px(px(theme::CONTENT_PAD_X))
                    .py(px(theme::CONTENT_PAD_Y))
                    .gap(px(16.))
                    .child(
                        v_flex()
                            .gap(px(3.))
                            .child(
                                div()
                                    .text_size(px(17.))
                                    .font_weight(FontWeight::SEMIBOLD)
                                    .child(self.tab.title()),
                            )
                            .child(
                                div()
                                    .text_size(px(12.5))
                                    .text_color(theme::muted())
                                    .child(self.tab.hint()),
                            ),
                    )
                    .child(body),
            )
    }
}

fn is_image(path: &Path) -> bool {
    matches!(
        path.extension()
            .and_then(|ext| ext.to_str())
            .map(|ext| ext.to_ascii_lowercase())
            .as_deref(),
        Some("png" | "jpg" | "jpeg" | "webp" | "tif" | "tiff" | "bmp")
    )
}

/// 追加图片路径,按小写全路径去重;返回真正新增的路径。
fn append_images(existing: &mut Vec<PathBuf>, images: Vec<PathBuf>) -> Vec<PathBuf> {
    let mut seen: Vec<String> = existing
        .iter()
        .map(|path| path.to_string_lossy().to_lowercase())
        .collect();
    let mut added = Vec::new();
    for path in images {
        let key = path.to_string_lossy().to_lowercase();
        if seen.contains(&key) {
            continue;
        }
        seen.push(key);
        existing.push(path.clone());
        added.push(path);
    }
    added
}

/// 追加图片路径,返回写进日志的一句中文描述(只列出真正新增的文件)。
fn append_drop_images(existing: &mut Vec<PathBuf>, images: Vec<PathBuf>, kinds: &str) -> String {
    let dropped = images.len();
    let added = append_images(existing, images);
    if dropped == 0 {
        return format!("拖入的内容里没有支持的图片({kinds})");
    }
    if added.is_empty() {
        return format!("拖入的 {dropped} 个文件都已在列表中");
    }
    let names: Vec<String> = added
        .iter()
        .take(3)
        .map(|path| {
            path.file_name()
                .map(|name| name.to_string_lossy().to_string())
                .unwrap_or_else(|| path.display().to_string())
        })
        .collect();
    let suffix = if added.len() > 3 { " 等" } else { "" };
    let skipped = dropped - added.len();
    let skipped_note = if skipped > 0 {
        format!(",跳过 {skipped} 个重复/不支持的文件")
    } else {
        String::new()
    };
    format!(
        "拖入 {} 张图片:{}{}{skipped_note},共 {} 张待处理",
        added.len(),
        names.join("、"),
        suffix,
        existing.len()
    )
}
fn main() {
    let app = gpui_kit::application().with_assets(Assets);
    app.run(move |cx| {
        gpui_kit::init(cx);
        theme::install(cx);

        // ATK_UI_WINDOW_POS="x,y,w,h":直接放到指定位置(截图脚本用它把窗口开在副屏)。
        let bounds = std::env::var("ATK_UI_WINDOW_POS")
            .ok()
            .and_then(|value| {
                let parts: Vec<f32> = value
                    .split(',')
                    .filter_map(|part| part.trim().parse::<f32>().ok())
                    .collect();
                (parts.len() == 4).then(|| {
                    WindowBounds::Windowed(Bounds::new(
                        point(px(parts[0]), px(parts[1])),
                        size(px(parts[2]), px(parts[3])),
                    ))
                })
            })
            .unwrap_or_else(|| WindowBounds::centered(None, size(px(1264.), px(861.)), cx));
        let options = WindowOptions {
            window_bounds: Some(bounds),
            titlebar: Some(TitlebarOptions {
                title: Some("Artist Toolkit".into()),
                appears_transparent: false,
                traffic_light_position: None,
            }),
            ..Default::default()
        };
        gpui_kit::open_window(options, cx, |window, cx| cx.new(|cx| Shell::new(window, cx)))
            .expect("failed to open window");
    });
}
