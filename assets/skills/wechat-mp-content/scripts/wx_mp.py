#!/usr/bin/env python3
"""WeChat Official Account (gong zhong hao) content reader - fast path.

Subcommands
-----------
probe                     Report local WeChat install/profile readability.
article <url|sn>          Fetch an mp.weixin.qq.com article, dump metadata/text/images.
comments <url|sn>         Fetch selected comments (elected_comment) + replies via the API.
auth <mid>                Locate a live WeChat-opened article URL (key/uin/pass_ticket).
search <keyword>          Search official-account articles through Sogou WeChat.

Why this exists
---------------
Comments are not in the page HTML and not shown to a logged-out browser: the page
renders an empty comment module and "write comment" answers "open this article in
WeChat". The comment API needs a WeChat session. The WeChat client's own browser
keeps the authenticated article URL (key/uin/pass_ticket) in a plain, unlocked
profile file named "Share Data". Read that first - it is where the time is saved.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import html as _html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import http.cookiejar

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
UA_WX = UA + " MicroMessenger/7.0.20(0x6700143B) WindowsWechat UnifiedPCWindowsWechat"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


_OPENER = None


def _opener():
    """Shared opener with a cookie jar: Sogou redirect links need the search cookies."""
    global _OPENER
    if _OPENER is None:
        _OPENER = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    return _OPENER


def http_get(url, referer=None, ua=UA, timeout=40):
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        **({"Referer": referer} if referer else {}),
    })
    with _opener().open(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", "replace")


def url_clean(s):
    """A URL glued to following text: keep ASCII 33..126, drop trailing '&'."""
    out = []
    for ch in s:
        if ord(ch) < 33 or ord(ch) > 126:
            break
        out.append(ch)
    return "".join(out).rstrip("&")


def fmt_ts(t):
    try:
        return _dt.datetime.fromtimestamp(int(t)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(t)


def ip_wording(rec):
    w = (rec or {}).get("ip_wording") or {}
    return w.get("province_name") or w.get("city_name") or w.get("country_name") or ""


def wechat_dirs():
    appdata = os.environ.get("APPDATA", "")
    cands = [os.path.join(appdata, "Tencent", "xwechat", "radium"),
             os.path.join(appdata, "Tencent", "xwechat"),
             os.path.join(appdata, "Tencent", "WeChat")]
    return [p for p in cands if os.path.isdir(p)]


def find_share_data():
    out = []
    for root in wechat_dirs():
        for pat in ("web/profiles/*/Share Data", "profiles/*/Share Data",
                    "web/profiles/*/*/Share Data", "**/Share Data"):
            out.extend(glob.glob(os.path.join(root, pat), recursive=True))
    return sorted(set(out), key=lambda p: -os.path.getmtime(p))


def profile_kind(path):
    m = re.search(r"(?:multitab|webview)_([0-9a-f]{32})", path)
    return m.group(1)[:4] if m else ""


def read_auth_params(mid, extra_files=()):
    """Find an authenticated article URL for `mid`; return [(file, url, params)]."""
    pat = re.compile(rb"https://mp\.weixin\.qq\.com/s\?__biz=[^\x00-\x20\"'<>]{60,}")
    hits = []
    for f in list(find_share_data()) + list(extra_files):
        try:
            blob = open(f, "rb").read()
        except OSError:
            continue
        for m in pat.finditer(blob):
            u = url_clean(m.group(0).decode("utf-8", "replace"))
            if ("mid=%s" % mid) not in u:
                continue
            q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
            if "key" in q and "pass_ticket" in q:
                hits.append((f, u, q))
    return hits


def norm(s):
    return _html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def article_meta(html_text, url=""):
    def first(*pats):
        for p in pats:
            m = re.search(p, html_text, re.S)
            if m:
                return _html.unescape(m.group(1)).strip()
        return ""

    meta = {
        "url": url,
        "title": first(r'<meta property="og:title" content="([^"]*)"',
                       r"window\.msg_title = .*?'([^']*)'",
                       r'<h1[^>]*id="activity-name"[^>]*>(.*?)</h1>'),
        "biz": first(r"window\.biz = [^\n]*?'([A-Za-z0-9+/=]{8,})'",
                     r"[?&]__biz=([A-Za-z0-9+/=%]+)"),
        "mid": first(r"window\.mid = [^\n]*?'(\d+)'",
                     r"window\.appmsgid = [^\n]*?'(\d+)'",
                     r"[?&]mid=(\d+)"),
        "idx": first(r"window\.idx = ([0-9]+)", r"[?&]idx=(\d+)") or "1",
        "sn": first(r"window\.sn = [^\n]*?'([0-9a-f]{16,})'", r"[?&]sn=([0-9a-f]{16,})"),
        "comment_id": first(r"comment_id:\s*'?(\d+)", r'"comment_id"\s*:\s*"?(\d+)'),
        "item_show_type": first(r"window\.item_show_type = '(\d+)'"),
        "publish_time": first(r"ori_create_time:\s*'(\d+)'"),
    }
    # Image-share posts (item_show_type=8) and many forwarded `src=11&signature=`
    # links omit window.biz / window.mid / window.idx from the page HTML. The
    # authoritative values are then in the URL query, and without them the comment
    # API answers {"ret": -3, "errmsg": "no session"} even when the session is live.
    if url:
        _q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        for _key, _param, _default in (("biz", "__biz", ""), ("mid", "mid", ""),
                                       ("idx", "idx", "1"), ("sn", "sn", "")):
            if not meta[_key]:
                _value = (_q.get(_param) or [_default])[0]
                if _value:
                    meta[_key] = _value
    body = ""
    m = re.search(r'<div class="rich_media_content[^"]*"[^>]*id="js_content"[^>]*>(.*?)</div>\s*<script',
                  html_text, re.S)
    if m:
        body = norm(re.sub(r"<(br|/p|/div)[^>]*>", "\n", m.group(1)))
        body = re.sub(r"\n{2,}", "\n", body)
    else:
        m = re.search(r'<div class="js_image_content"[^>]*>(.*?)</div>\s*<div', html_text, re.S)
        if m:
            body = norm(m.group(1))
    meta["text"] = body
    imgs, seen = [], set()
    for u in re.findall(r'https://mmbiz\.qpic\.cn/[A-Za-z0-9_\-/=]+[^"\'\s<> ]*', html_text):
        u = _html.unescape(u)
        if u not in seen:
            seen.add(u)
            imgs.append(u)
    meta["images"] = imgs
    return meta


def fetch_article(url):
    if url and re.fullmatch(r"[A-Za-z0-9_\-]{16,}", url):
        url = "https://mp.weixin.qq.com/s/" + url
    text = http_get(url, ua=UA_WX)
    return text, article_meta(text, url)


def fetch_comments(meta, auth, limit=100):
    q = auth
    params = {
        "action": "getcomment", "scene": "0",
        "appmsgid": meta["mid"], "idx": meta.get("idx") or "1",
        "comment_id": meta["comment_id"], "offset": "0", "limit": str(limit),
        "biz": meta["biz"], "uin": q.get("uin", ""), "key": q.get("key", ""),
        "pass_ticket": q.get("pass_ticket", ""),
        "devicetype": q.get("devicetype") or "UnifiedPCWindows",
        "version": q.get("version", ""), "lang": "zh_CN", "countrycode": "CN",
        "appmsg_token": "", "x5": "0", "f": "json",
        "is_need_ad": "0", "is_need_ticket": "0",
    }
    api = "https://mp.weixin.qq.com/mp/appmsg_comment?" + urllib.parse.urlencode(params)
    return json.loads(http_get(api, referer=meta.get("referer") or meta["url"]))


def render_comments(data):
    cs = data.get("elected_comment") or []
    lines = ["# visible elected comments: %d ; total_count=%s elected=%s continue=%s" % (
        len(cs), data.get("total_count"), data.get("elected_comment_total_cnt"),
        data.get("continue_flag"))]
    n_rep = 0
    for i, c in enumerate(cs, 1):
        lines.append("\n[%02d] %s (likes=%s, %s, %s)" % (
            i, c.get("nick_name", ""), c.get("like_num", 0), ip_wording(c),
            fmt_ts(c.get("create_time"))))
        for ln in (c.get("content") or "").split("\n"):
            lines.append("     " + ln)
        for r in ((c.get("reply_new") or {}).get("reply_list") or []):
            n_rep += 1
            lines.append("     -> %s (likes=%s, %s): %s" % (
                r.get("nick_name", ""), r.get("like_num", 0), ip_wording(r),
                (r.get("content") or "").replace("\n", " ")))
    lines.append("\n# replies: %d" % n_rep)
    return "\n".join(lines)


def sogou_search(keyword, max_n=10):
    url = "https://weixin.sogou.com/weixin?" + urllib.parse.urlencode(
        {"type": "2", "query": keyword, "ie": "utf8"})
    page = http_get(url, referer="https://weixin.sogou.com/")
    if re.search(r"antispider|seccode|captcha", page, re.I):
        return {"error": "sogou_antispider", "results": []}
    blocks = re.findall(r"<li id=\"sogou_vr_11002601_box_\d+\"(.*?)</li>", page, re.S)
    if not blocks:
        blocks = re.findall(r"<li[^>]*class=\"[^\"]*news-box[^\"]*\"(.*?)</li>", page, re.S)
    items = []
    for block in blocks:
        tm = re.search(r"<h3>.*?<a[^>]*>(.*?)</a>", block, re.S)
        acct = re.search(r'class="account"[^>]*>(.*?)<', block, re.S) or \
               re.search(r'<span class="all-time-y2">(.*?)</span>', block, re.S)
        summ = re.search(r'class="txt-info"[^>]*>(.*?)</p>', block, re.S)
        link = re.search(r'href="(/link\?url=[^"]+)"', block)
        items.append({
            "title": norm(tm.group(1)) if tm else "",
            "account": norm(acct.group(1)) if acct else "",
            "summary": norm(summ.group(1)) if summ else "",
            "sogou_link": ("https://weixin.sogou.com"
                           + _html.unescape(link.group(1)).replace(" ", "%20")) if link else "",
            "url": "",
        })
    for it in items[:max_n]:
        if it["sogou_link"]:
            try:
                red = http_get(it["sogou_link"], referer="https://weixin.sogou.com/")
                real = "".join(re.findall(r"url \+= '([^']*)';", red)).replace("@", "")
                if real.startswith("https://mp."):
                    it["url"] = real
            except Exception as e:
                it["error"] = str(e)
    return {"error": None, "results": items[:max_n]}


def cmd_probe(_args):
    print("## WeChat data dirs")
    for d in wechat_dirs():
        print("  ", d)
    sd = find_share_data()
    print("## 'Share Data' stores (auth-param source): %d" % len(sd))
    for f in sd[:10]:
        try:
            open(f, "rb").close()
            ok = "readable"
        except OSError:
            ok = "LOCKED"
        print("   %-8s %8d  [acct %s] %s" % (ok, os.path.getsize(f), profile_kind(f), os.path.normpath(f)))
    print("## next: python wx_mp.py auth <mid>")


def cmd_auth(args):
    hits = read_auth_params(args.mid)
    if not hits:
        print("NO AUTH URL for mid=%s" % args.mid)
        print("Open the article once inside WeChat, then re-run.")
        return 1
    f, u, q = hits[0]
    print("source:", f)
    print("url:", u)
    for k in ("__biz", "mid", "idx", "sn", "chksm", "key", "uin", "pass_ticket",
              "devicetype", "version", "sessionid", "scene"):
        if k in q:
            v = q[k][0]
            print("   %-12s %s" % (k, (v[:20] + "..." if len(v) > 24 else v)))
    return 0


def cmd_article(args):
    html_text, meta = fetch_article(args.url)
    os.makedirs(args.out, exist_ok=True)
    open(os.path.join(args.out, "article.html"), "w", encoding="utf-8").write(html_text)
    json.dump(meta, open(os.path.join(args.out, "article.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("title :", meta["title"])
    print("biz   :", meta["biz"], "| mid:", meta["mid"], "| idx:", meta["idx"])
    print("sn    :", meta["sn"])
    print("cid   :", meta["comment_id"], "(required by the comment API)")
    print("type  :", meta["item_show_type"], "(8 = image-share post)")
    print("images:", len(meta["images"]))
    print("text  :", (meta["text"] or "")[:200])
    print("saved :", os.path.join(args.out, "article.json"))
    return 0


def cmd_comments(args):
    _, meta = fetch_article(args.url)
    if args.uin and args.key and args.pass_ticket:
        auth = {"uin": args.uin, "key": args.key, "pass_ticket": args.pass_ticket,
                "devicetype": args.devicetype, "version": args.version}
        src = "cli"
    else:
        hits = read_auth_params(meta["mid"])
        if not hits:
            print("NO WeChat session params for mid=%s." % meta["mid"])
            print("Open the article once in WeChat, or pass --uin/--key/--pass-ticket.")
            return 1
        f, auth_url, q = hits[0]
        auth = {k: q.get(k, [""])[0] for k in ("key", "uin", "pass_ticket", "devicetype", "version")}
        meta["referer"] = auth_url
        src = f
    data = fetch_comments(meta, auth, limit=args.limit)
    ret = (data.get("base_resp") or {}).get("ret")
    if ret != 0:
        print("API ret=%s errmsg=%s" % (ret, data.get("errmsg")))
        if str(ret) == "-3":
            print("  -> WeChat session key EXPIRED (typical lifetime is tens of minutes).")
            print("     Ask the user to open/re-open the article in WeChat, then re-run immediately.")
        if str(ret) == "-2":
            print("  -> invalid args: comment_id/biz/mid wrong or missing.")
        return 2
    os.makedirs(args.out, exist_ok=True)
    json.dump(data, open(os.path.join(args.out, "comments.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    text = render_comments(data)
    open(os.path.join(args.out, "comments.txt"), "w", encoding="utf-8").write(text)
    print("auth source:", src)
    print(text[:1500])
    print("\nsaved:", os.path.join(args.out, "comments.txt"))
    return 0


def cmd_search(args):
    res = sogou_search(args.keyword, args.n)
    if res.get("error"):
        print("ERROR:", res["error"], "(Sogou throttled; retry later)")
        return 1
    for i, it in enumerate(res["results"], 1):
        print("[%02d] %s" % (i, it["title"]))
        print("     account:", it["account"])
        print("     url    :", it["url"] or "(unresolved)")
        if it.get("summary"):
            print("     summary:", it["summary"][:120])
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="WeChat Official Account reader")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe").set_defaults(func=cmd_probe)

    a = sub.add_parser("article"); a.add_argument("url"); a.add_argument("--out", default="wx_out")
    a.set_defaults(func=cmd_article)

    c = sub.add_parser("comments"); c.add_argument("url"); c.add_argument("--out", default="wx_out")
    c.add_argument("--limit", type=int, default=100)
    c.add_argument("--uin"); c.add_argument("--key"); c.add_argument("--pass-ticket")
    c.add_argument("--devicetype"); c.add_argument("--version")
    c.set_defaults(func=cmd_comments)

    t = sub.add_parser("auth"); t.add_argument("mid"); t.set_defaults(func=cmd_auth)
    s = sub.add_parser("search"); s.add_argument("keyword"); s.add_argument("-n", type=int, default=10)
    s.set_defaults(func=cmd_search)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
