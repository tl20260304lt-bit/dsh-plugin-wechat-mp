---
name: wechat-mp-content
description: Read 微信公众号 (mp.weixin.qq.com) articles, their 留言/comments, and search 公众号 articles by keyword. Use when a WeChat article link must be read or its comments analyzed, when the page shows 暂无留言 / 即将前往微信打开此文章, or when searching WeChat official-account content. Not for general web search.
metadata:
  short-description: 公众号正文与留言
---

# 公众号内容高效获取

微信公众号的正文和评论走两套不同的通道，且评论有会话时效。**顺序错了会浪费大量时间**——本技能的核心就是顺序。

## 前置条件

- **Windows 上的微信 PC 客户端**：会话参数来自 `%APPDATA%\Tencent\xwechat`（或旧版 `Tencent\WeChat`）下的 `Share Data` 文件。macOS / Linux 没有这个文件，本技能不适用。
- **Python 3.9+**，只用标准库（`urllib`、`json`、`re`、`glob`），**不需要 pip 安装任何包**。
- 所有脚本在本技能基础目录的 `scripts/` 下。基础目录见 `<skill_resources>` 给出的 Base directory，下文用 `<skill>` 指代它，**实际执行时换成绝对路径并加引号**（路径可能含空格）。

In DeepSeek Harness, run these through the persistent shell. `<skill>` is documentation-only shorthand: always substitute the real absolute base directory before running a command.

## 第一原则：先拿会话，再取评论

评论接口 `mp/appmsg_comment` 需要微信客户端内的会话参数（`uin` / `key` / `pass_ticket`），它们**只在几十分钟内有效**。这些参数以明文保存在微信内置浏览器的一个**未加锁**文件 `Share Data` 里。

因此：

1. 用户给出文章链接后，**第一步就去本地取会话参数并调评论接口**。
2. 如果失败再退回读正文、找镜像、OCR。
3. 绝不要先花时间在浏览器/搜索引擎/缓存考古上——那些做完，会话已经过期。

## 快速路径

```bash
python "<skill>/scripts/wx_mp.py" probe                       # 本机微信数据目录与 Share Data 可读性
python "<skill>/scripts/wx_mp.py" article  <url|sn>  --out OUT   # 标题/__biz/mid/idx/sn/comment_id/图片/正文
python "<skill>/scripts/wx_mp.py" comments <url|sn>  --out OUT   # 精选留言 + 回复（必须先做这步）
python "<skill>/scripts/wx_mp.py" search   "<关键词>" -n 10       # 搜狗微信搜索 → 真实 mp.weixin.qq.com 链接
```

`article` 输出的 `comment_id` 是评论接口的必需参数；缺它会返回 `ret=-2 invalid args`。

### 会话参数从哪来

- 来源：`%APPDATA%\Tencent\xwechat\radium\web\profiles\multitab_<hash>\Share Data`
- 内容：微信客户端打开/分享文章时的完整 URL，含 `key`、`uin`、`pass_ticket`、`exportkey`
- 特征：该文件**不加锁**（同目录下的 `Network\Cookies` 是独占锁，拿不到，别浪费时间）
- 账户映射：profile 目录 hash 的**前 4 位十六进制** = 微信文件目录 `wxid_*_<4位>` 的后缀
- 前提：用户必须曾在**微信客户端内**打开过该文章（PC 端或手机同步均可）

`python "<skill>/scripts/wx_mp.py" auth <mid>` 可直接列出某个 `mid` 找到的会话 URL，便于排查。

## 已验证的事实与边界（不要重复试探）

| 事实 | 证据 |
|---|---|
| 网页版登录态下**看不到**评论 | DOM 中 `#js_cmt_container` 带 `rich_media_extra_discuss_empty` 且 `display:none`，另有隐藏的"暂无留言" |
| 点"写留言"会被导流回 App | 弹窗原文：*"即将前往微信打开此文章，使用完整服务。"* |
| 无会话直调接口 | `{"ret":-3,"errmsg":"no session","cookie_count":0}` |
| 缺 `comment_id` | `ret=-2, invalid args` |
| 成功 | `base_resp.ret=0`，返回 `elected_comment` 数组 |
| 只有"精选"评论公开 | `elected_comment_total_cnt`（可见）常小于 `total_count`（总条数）；其余评论**无公开接口** |
| 分页无效 | `offset=20/40` 仍返回同一批 `elected_comment`，`continue_flag=false` 即到底 |
| 图片分享类短文 | `item_show_type=8`（`page_share_img`），评论区为 App 专属，正文多为图片 |

## 正文与图片

- 普通图文：正文在 `<div id="js_content">`，`article` 命令已提取为 `text`。
- **图片分享短文（`item_show_type=8`）与搜狗/转发链接（`src=11&signature=`）的页面 HTML 里没有 `window.biz` / `window.mid`**。脚本会退回 URL 查询参数取 `__biz` / `mid` / `idx` / `sn`——这是必须的：缺 `mid` 时评论接口会假报 `ret=-3 no session`，会话明明还是活的。
- 如果链接本身也不含这些参数（短链 `/s/<sn>`、搜狗签名链），先在 `Share Data` 里找到该文的**规范 URL**（带 `__biz=` / `mid=` 的那条，`auth <mid>` 或直接扫最近条目），再对它跑 `comments`。
- 图片分享短文：正文是图片（`mmbiz.qpic.cn` URL 列在 `images`）。文本模型**不能直接看图**，需要 OCR：见 `references/ocr-and-limits.md`（Windows 内置 OCR `zh-Hans-CN` 已实测可用）。
- 图片多为 EDA 截图，OCR 常常只能拿到水印；不要把 OCR 文本当作可靠证据，能拿到正文 HTML 就以 HTML 为准。

## 搜索

- 可用：搜狗微信 `https://weixin.sogou.com/weixin?type=2&query=<关键词>`，返回标题/公众号/摘要/日期，跟随 `/link?url=...` 重定向可解析出真实文章 URL。
- 必须带 cookie（脚本内部用共享 CookieJar）；链接里的空格要转义为 `%20`，否则 `InvalidURL`。
- 搜狗可能返回反爬页（`antispider`/`captcha`），此时换关键词或稍后重试，不要连续猛刷。
- 站外搜索引擎对公众号内容覆盖很差（Bing/Baidu/DDG 基本搜不到正文和评论），不要作为主路径。

## 不要做的事（踩过的坑）

- 不要指望登录态网页版能看评论——它会提示"前往微信"。
- 不要用手机 UA、镜像站、`r.jina.ai` 去凑——要么拿不到评论，要么直接撞验证码。
- 不要去复制 `Network\Cookies`（独占锁，`esentutl`/共享读/备份 API 都失败）。
- 不要用系统级 UI 自动化去驱动微信窗口（窗口常是最小化状态）。
- 不要在没拿到会话前先去做 OCR、图片下载、格式整理。

## 会话过期后的处理

若 `comments` 返回 `ret=-3 no session`：

1. 让用户**在微信里重新打开（或刷新）该文章**一次；
2. 立刻重跑 `comments`（`Share Data` 会写入新的 `key`）。

`key` 的生命周期以"几十分钟"量级估计；不要把一次成功的会话参数缓存起来当长期凭据。

## 输出与引用

- 引用评论时保留：昵称、点赞数、IP 归属（`ip_wording`）、时间（`create_time`，本地时区）。
- 明确区分"可见的精选留言 N 条"与"接口报告的 total_count"，不要把两者混为一谈。
- 载荷细节与错误码对照见 `references/troubleshooting.md`。
