---
name: wechat-mp-corpus
description: Build a local article corpus from a WeChat official account (公众号) on Windows by watching the WeChat PC client's "Share Data" for articles the user opens, then auto-downloading each article's text and images. Use when the user wants to archive or mirror a 公众号's articles locally, continue an existing corpus, or when a 公众号's history API returns an empty list.
metadata:
  short-description: 微信文章本地存档
---

# 微信公众号文章本地存档

把「你在微信里点开的文章」自动变成一份本地文章库（正文 + 原始页面 + 全部配图 + 索引）。

## 前置条件

- **Windows 上的微信 PC 客户端**（脚本只读 `%APPDATA%\Tencent\xwechat` 下的 `Share Data`）。
- **Python 3.9+**，只用标准库，**不需要 pip 安装任何包**。
- 脚本位于本技能基础目录的 `scripts/`；下文 `<skill>` 指 `<skill_resources>` 给出的 Base directory，**执行时替换为绝对路径并加引号**。

## 核心原理（这是本技能存在的理由）

微信 PC 端**每打开一篇 `mp.weixin.qq.com/s` 文章**，就会把该文章的**完整 URL**
（含 `__biz`、`mid`、`idx`、`sn`、`chksm`、会话 `key`）写进一个**不加锁、可读**的文件：

```
%APPDATA%\Tencent\xwechat\radium\web\profiles\multitab_<hash>\Share Data
```

拿到的 URL 带 `chksm`，**可以直接用普通 HTTP GET 抓到完整正文**（不需要登录态、不需要 cookie）。

于是最可靠的采集姿势不是"调列表接口"，而是：

> **让用户在微信里翻公众号历史消息、逐篇点开 → 本地脚本盯着 Share Data → 发现新文章就自动下载。**

这条路径对**任何**公众号都成立，包括"历史消息接口返回空列表"的号（贴图号/图片号、
仅"发布"未"群发"的号）。其它思路的失败原因见 `references/why-other-approaches-fail.md`。

## 工作流

### 1. 探环境 + 确定目标号

```bash
python "<skill>/scripts/probe_env.py"
```

列出可读的 `Share Data`、微信进程，以及**里面已经出现过的公众号**（按 `__biz` 统计）。
如果用户给了一篇目标号的文章链接：

```bash
python "<skill>/scripts/probe_env.py" --url "<mp.weixin.qq.com/s/... 或 /s?__biz=...>"
```

输出该号的 `__biz`，以及它当前已出现在缓存里的文章数。

### 2. 启动归档哨兵

```bash
python "<skill>/scripts/watch_corpus.py" --biz "<__biz>" --out "<语料目录>" --interval 3
```

- 每 `--interval` 秒扫一次所有 `Share Data`
- 发现该 `__biz` 的**新**文章（按 `mid` 去重）就立刻下载
- **可反复运行**：已下载的会跳过（状态存在 `<语料目录>/../.watcher_state.json`，可用 `--state` 指定）
- 可随时 Ctrl-C；下次接着跑，不会重复

在 DSH 里这是一个长任务：用 `run_in_background` 的 shell 作业启动它，不要占用前台命令槽。

### 3. 让用户去点

请用户在微信里打开该号，**一篇一篇点开、点开就关**。每点一篇，几秒内自动入库。

- 不用管顺序；重复点会自动跳过
- 分批也行：点累了就停，之后重新启动哨兵继续

### 4. 出索引

```bash
python "<skill>/scripts/build_index.py" --corpus "<语料目录>"
```

生成 `_index.csv`（日期/标题/mid/字数/图片数/原始链接）和 `README.md`。

## 输出结构

```
<语料目录>/
├─ _index.csv          ★ 全库索引
├─ README.md
└─ <YYYY-MM-DD>_<标题>_<mid>/
   ├─ article.md       正文（Markdown，带来源头）
   ├─ article.html     原始页面（离线留档）
   ├─ meta.json        标题/作者/发布时间/图片清单
   └─ images/001.jpg…  全部配图
```

## 约束与注意

- **必须有用户点击**：没有可靠的公开接口能列出任意公众号的全部文章；
  不要在这上面浪费时间（`references/why-other-approaches-fail.md` 记录了实测过的死路）。
- **只采集用户有权访问的公开文章**，供个人研读，不要二次分发。
- 只写日志到语料目录，**不要修改微信数据、不要注入微信进程**。
- 慢一点没关系：`--interval 3` 足够；**别把间隔调到 1 秒以下**，没有收益还可能丢请求。
- 下载失败的条目会在状态里记 `{"error": "fetch"}`；想重试删掉该条目再跑，或加 `--retry-failed`。

## 参考

- `references/why-other-approaches-fail.md` — 各条死路的实测结论（避免重复踩坑）
- `references/share-data-format.md` — Share Data 里 URL 的字段含义与定位方法
