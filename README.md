# dsh-plugin-wechat-mp

[中文说明](README.zh.md) · [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) plugin · MIT

WeChat official account (公众号) skills for DeepSeek Harness. Two skills, no MCP server, no third-party Python, no cloud round-trip:

| Skill | What it does |
|---|---|
| `wechat-mp-content` | Read an `mp.weixin.qq.com` article **and its 留言/comments**, using the live session the WeChat PC client keeps in its own unlocked `Share Data` file. Also searches 公众号 articles by keyword. |
| `wechat-mp-corpus` | Archive a whole 公众号 locally: watch `Share Data` while you click through the account's history, then auto-download each new article's text, original HTML, and images into an indexed corpus. |

Both skills exist because of one hard fact: **article bodies are easy, comments are not.** A logged-out browser is served an empty comment module and "open this article in WeChat"; the comment API (`mp/appmsg_comment`) needs `uin` / `key` / `pass_ticket`, which only exist inside the WeChat client's browser profile — in a plain, unlocked file. Reading that file first is the whole trick. Everything else in the skills (the failed approaches, the error codes, the pagination dead end) is there so an agent does not re-discover it the slow way.

## Requirements

- **Windows** with the WeChat PC client — the session source is `%APPDATA%\Tencent\xwechat\radium\web\profiles\multitab_<hash>\Share Data` (older installs: `%APPDATA%\Tencent\WeChat`).
- **Python 3.9+** on `PATH`. The helpers use the standard library only — `pip install` is not needed.
- **DeepSeek Harness** with the skill registry mounted (any profile built on `dsh-base`, e.g. `web` or `desktop`).
- Node.js 20+ for the plugin itself (the host provides it).

## Install

The plugin is a DSH bundle: installing it adds one row to the profile's Cordis tree, which registers a read-only skill provider.

```sh
# from a local checkout
dsh plugin --profile desktop add C:/path/to/dsh-plugin-wechat-mp

# or from the registry, once published
dsh plugin --profile desktop add dsh-plugin-wechat-mp
```

`dsh plugin` appends the bundle to `dsh.profile.bundles` automatically. Alternatively, use the **Plugins** page in the Web UI (sidebar → Plugins) and install from a path or package name.

### Market index

DSH's **Plugins → Discover** reads plugin-market indexes (format 1). This repository publishes one:

```
https://tl20260304lt-bit.github.io/dsh-plugin-wechat-mp/market/index.json
```

Open **Plugins → Discover → Add index source**, paste that URL, and the entry installs `dsh-plugin-wechat-mp@<version>` from npm. After a release, regenerate and check it with `npm run market:build && npm run market:check`.

After the profile loads, the two skills appear in the agent's skill catalog. With HMR enabled in the profile — the default for `dsh-base` profiles — the catalog updates **without restarting**: the new skills are visible in the very next turn. Otherwise restart the app.

Verify:

```sh
node --test                                   # 10 checks: provider contract, catalog, bodies, portability
python -m unittest discover -s test -p "test_*.py"   # 4 checks: URL-query fallback for biz/mid/idx/sn
```

## Use

Just ask. The skills are model-invocable and user-invocable, so either of these works:

- "读一下这篇文章和它的留言：https://mp.weixin.qq.com/s/…"
- "把这个公众号的文章都存档到 D:\wx_corpus\某号"
- `/wechat-mp-content` (explicit invocation, if your UI exposes skill commands)

The article and comment helpers are also directly runnable — the skills tell the agent to substitute the base directory the runtime reports:

```sh
python "<skill>/scripts/wx_mp.py" probe
python "<skill>/scripts/wx_mp.py" article  <url|sn> --out OUT
python "<skill>/scripts/wx_mp.py" comments <url|sn> --out OUT
python "<skill>/scripts/wx_mp.py" search   "关键词" -n 10
```

## How it works

```
dsh-plugin-wechat-mp/
├─ package.json            # "dsh.bundle.patch" → cordis.patch.yml
├─ cordis.patch.yml        # inserts row: id skill-wechat-mp
├─ lib/index.js            # ~200 lines, zero dependencies
└─ assets/skills/
   ├─ wechat-mp-content/   # SKILL.md + references/ + scripts/wx_mp.py
   └─ wechat-mp-corpus/    # SKILL.md + references/ + scripts/
```

`lib/index.js` exports the Cordis plugin triple `name` / `inject` / `apply`. `apply` registers one provider on `ctx.skills`; the provider enumerates `assets/skills/*/SKILL.md`, parses the frontmatter, and returns the candidates. Bodies are read from disk on demand (`get`), so a skill costs nothing until it is loaded, and a missing or broken asset tree yields an empty catalog instead of taking down the profile.

Each skill's `resourceBase` is its own directory, which is what makes the instructions portable: the runtime hands the model "Base directory for this skill: …", and the skills say `scripts/wx_mp.py` / `references/…` relative to it. No absolute path is hardcoded anywhere — a regression test enforces that.

## Porting a Codex skill bundle

The layout is deliberately close to a Codex plugin (`.codex-plugin/plugin.json` + `skills/`), so the port is mechanical:

| Codex | DeepSeek Harness |
|---|---|
| `.codex-plugin/plugin.json` (name, interface, `skills: "./skills/"`) | `package.json` with `dsh.bundle.patch` + `keywords` |
| `skills/<name>/SKILL.md` + `references/` + `scripts/` | identical under `assets/skills/<name>/` |
| `agents/openai.yaml` (per-skill UI hints) | dropped; `metadata.short-description` kept |
| Codex loads the folder | a ~40-line provider registers the same tree on `ctx.skills` |
| absolute script paths from the install location | relative paths + `resourceBase` |

Only the path convention and the registration glue change; the instructions and helper scripts ship unchanged.

## Limitations, by design

- **Windows only.** The session and the archive watcher both depend on the WeChat PC client's `Share Data`. There is no macOS/Linux equivalent in this plugin.
- **You must open the article in WeChat.** Session parameters live for tens of minutes; after `ret=-3 no session`, reopen the article and rerun.
- **Only 精选 comments are public.** `elected_comment` is what the API returns; `elected_comment_total_cnt` can be smaller than `total_count` and the rest has no public endpoint. Pagination does not work (`offset` is ignored, `continue_flag=false` means end).
- **Image-only posts** need OCR; the skill documents the Windows `zh-Hans-CN` path and warns that OCR text is not reliable evidence.
- **No listing API.** Archiving requires the user to click through the account's history in WeChat — that is the reliable path, not a workaround.
- **Read-only.** Nothing writes to the WeChat data directory, injects into the client, or copies the locked `Network\Cookies` store.

## Privacy

The plugin reads local WeChat files and fetches public `mp.weixin.qq.com` pages. It contains no telemetry, no analytics, and no remote endpoint of its own. Archived corpora are written wherever you point `--out`. Only collect articles you are entitled to read, and do not redistribute them.

## License

MIT © 2026 TaoLiu
