# Changelog

## 0.1.0 — 2026-10-31

First release. Two bundled skills, no runtime dependencies.

### Added

- `wechat-mp-content`: read an `mp.weixin.qq.com` article and its 精选留言 through the
  live WeChat PC client session, plus 搜狗微信 search. Ships `wx_mp.py`
  (`probe` / `article` / `comments` / `auth` / `search`).
- `wechat-mp-corpus`: watch the WeChat client's `Share Data` while the user clicks
  through an account's history, then auto-download each new article's text, original
  HTML, and images into an indexed corpus. Ships `probe_env.py`, `watch_corpus.py`,
  `build_index.py`.
- Cordis bundle: `lib/index.js` registers a read-only `ctx.skills` provider over
  `assets/skills/*/SKILL.md`; bodies load on demand and a broken asset tree degrades
  to an empty catalog instead of failing the profile.
- Format-1 plugin-market index (`market/index.json`) with an offline validator that
  mirrors DSH's `@deepseek-ai/dsh-plugin-market-index` rules.

### Fixed

- `article_meta` lost `biz` / `mid` / `idx` / `sn` for image-share posts
  (`item_show_type=8`) and forwarded `src=11&signature=` links, because those pages
  carry no `window.biz` / `window.mid`. The comment API then answered
  `{"ret": -3, "errmsg": "no session"}` for a perfectly valid session. The values now
  fall back to the URL query; found while reading a real 图片分享 article.

### Tests

- 10 Node checks (provider contract, catalog, bodies, path portability).
- 4 Python checks (URL-query fallback for `biz` / `mid` / `idx` / `sn`).
- `npm run pack:verify` loads both skills out of the packed tarball.
