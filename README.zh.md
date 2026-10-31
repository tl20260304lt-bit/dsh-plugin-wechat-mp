# dsh-plugin-wechat-mp

[English](README.md) · [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 插件 · MIT

给 DeepSeek Harness 装上微信公众号能力。两个技能，不依赖 MCP 服务，不装第三方 Python 包，也不经过任何中转服务：

| 技能 | 作用 |
|---|---|
| `wechat-mp-content` | 读取 `mp.weixin.qq.com` 文章**及其留言**——直接复用微信 PC 客户端自己留在 `Share Data` 里的会话参数；同时支持按关键词搜公众号文章。 |
| `wechat-mp-corpus` | 把一整个公众号本地存档：你翻历史消息逐篇点开，脚本盯着 `Share Data`，把每篇新文章的正文、原始 HTML、全部配图自动下载并建索引。 |

两个技能都源于同一个硬事实：**正文好拿，留言拿不到。** 未登录的浏览器只会看到空评论区加一句"前往微信打开"，而评论接口 `mp/appmsg_comment` 需要 `uin` / `key` / `pass_ticket`，它们只存在于微信客户端内置浏览器的 profile 目录里，是一个**不加锁**的明文文件。先读它，是这套方案的全部诀窍；技能里的失败路径、错误码、分页死路，是为了让 Agent 不必再把坑重踩一遍。

## 环境要求

- **Windows**，且安装微信 PC 客户端。会话来源是 `%APPDATA%\Tencent\xwechat\radium\web\profiles\multitab_<hash>\Share Data`（旧版为 `%APPDATA%\Tencent\WeChat`）。
- **Python 3.9+** 在 `PATH` 中。helper 只用标准库，**不需要 `pip install`**。
- **DeepSeek Harness**，且挂载了技能注册表（任何基于 `dsh-base` 的 profile，如 `web`、`desktop`）。
- 插件自身需要 Node.js 20+（由宿主提供）。

## 安装

插件是一个 DSH bundle：安装后向 profile 的 Cordis 树插入一行，注册一个只读技能提供者。

```sh
# 从本地目录安装
dsh plugin --profile desktop add C:/path/to/dsh-plugin-wechat-mp

# 发布到 npm 之后也可以直接按包名安装
dsh plugin --profile desktop add dsh-plugin-wechat-mp
```

`dsh plugin` 会自动把该 bundle 追加到 `dsh.profile.bundles`。也可以走 Web 界面：侧边栏 → **Plugins** → 按路径或包名安装。

### 插件市场索引

DSH 的 **Plugins → Discover** 读的是「插件市场索引」（format 1）。本仓库已经发布了一个：

```
https://tl20260304lt-bit.github.io/dsh-plugin-wechat-mp/market/index.json
```

在 **Plugins → Discover → Add index source** 里粘这条 URL，就能直接安装 `dsh-plugin-wechat-mp@<版本>`（走 npm）。每次发版后重新生成并自检：`npm run market:build && npm run market:check`。

profile 加载后，两个技能就出现在 Agent 的技能目录里。`dsh-base` 系列 profile 默认开启 HMR，因此**通常不需要重启**——下一轮对话即可见；若未开启，重启应用生效。

自检：

```sh
node --test                                    # 10 项：插件契约、技能目录、正文加载、路径可移植性
python -m unittest discover -s test -p "test_*.py"   # 4 项：biz/mid/idx/sn 的 URL 兜底逻辑
```

## 使用

直接说需求即可，技能既可被模型调用，也可手动调用：

- 「读一下这篇文章和它的留言：https://mp.weixin.qq.com/s/…」
- 「把这个公众号的文章都存到 D:\wx_corpus\某号」
- `/wechat-mp-content`（界面支持技能命令时显式调用）

底层脚本也可以单独跑，技能会要求 Agent 把运行时给出的基础目录代入 `<skill>`：

```sh
python "<skill>/scripts/wx_mp.py" probe
python "<skill>/scripts/wx_mp.py" article  <url|sn> --out OUT
python "<skill>/scripts/wx_mp.py" comments <url|sn> --out OUT
python "<skill>/scripts/wx_mp.py" search   "关键词" -n 10
```

## 实现方式

```
dsh-plugin-wechat-mp/
├─ package.json            # "dsh.bundle.patch" → cordis.patch.yml
├─ cordis.patch.yml        # 插入一行：id skill-wechat-mp
├─ lib/index.js            # 约 200 行，零运行时依赖
└─ assets/skills/
   ├─ wechat-mp-content/   # SKILL.md + references/ + scripts/wx_mp.py
   └─ wechat-mp-corpus/    # SKILL.md + references/ + scripts/
```

`lib/index.js` 导出 Cordis 插件的三件套 `name` / `inject` / `apply`。`apply` 在 `ctx.skills` 上注册一个 provider：枚举 `assets/skills/*/SKILL.md`、解析 frontmatter、返回候选技能；正文在 `get` 时才读盘，因此未被调用的技能不占上下文，资源目录缺失或损坏时只会得到空目录，而不会拖垮整个 profile。

每个技能的 `resourceBase` 指向它自己的目录，这是指令可移植的关键：运行时把「Base directory for this skill: …」交给模型，技能内部一律写 `scripts/wx_mp.py`、`references/…` 这样的相对路径。整个仓库没有硬编码绝对路径——这一点由回归测试守着。

## 从 Codex 技能包迁移

目录结构与 Codex 插件（`.codex-plugin/plugin.json` + `skills/`）刻意保持一致，迁移几乎是机械劳动：

| Codex | DeepSeek Harness |
|---|---|
| `.codex-plugin/plugin.json`（name、interface、`skills: "./skills/"`） | `package.json` 里的 `dsh.bundle.patch` + `keywords` |
| `skills/<name>/SKILL.md` + `references/` + `scripts/` | 原样放到 `assets/skills/<name>/` |
| `agents/openai.yaml`（每技能的 UI 提示） | 丢弃；保留 `metadata.short-description` |
| Codex 直接扫描目录 | 约 40 行 provider 把同一棵树注册到 `ctx.skills` |
| 安装位置相关的绝对脚本路径 | 相对路径 + `resourceBase` |

真正需要改的只有路径约定和注册胶水；技能正文与 Python 脚本可以原封不动地搬过来。

## 边界（设计如此）

- **仅 Windows。** 会话读取与归档监听都依赖微信 PC 客户端的 `Share Data`，本插件没有 macOS / Linux 的等价实现。
- **必须先在微信里打开过该文章。** 会话参数生命周期以「几十分钟」计；出现 `ret=-3 no session` 时，让用户重新打开文章后立即重跑。
- **只有「精选」留言公开。** 接口返回的是 `elected_comment`；`elected_comment_total_cnt` 可能小于 `total_count`，其余留言没有公开接口。分页无效（`offset` 被忽略，`continue_flag=false` 即到底）。
- **图片型短文**需要 OCR；技能里记录了 Windows `zh-Hans-CN` 的可行路径，并明确提醒 OCR 文本不能当可靠证据。
- **没有列表接口。** 归档必须由用户手动翻历史消息——这是唯一可靠路径，不是偷懒。
- **只读。** 不写微信数据目录、不注入微信进程、不复制被独占锁的 `Network\Cookies`。

## 隐私

插件只读本机微信文件、抓取公开的 `mp.weixin.qq.com` 页面。没有遥测、没有数据分析、没有自己的远程端点。存档写到 `--out` 指定的位置。请只采集你有权阅读的文章，不要二次分发。

## 许可

MIT © 2026 TaoLiu
