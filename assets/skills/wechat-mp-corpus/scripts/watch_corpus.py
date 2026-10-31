#!/usr/bin/env python3
r"""Watch WeChat's 'Share Data' for newly-opened articles of one official account and archive them.

Each article the user opens in the WeChat PC client is written (with __biz/mid/sn/chksm)
into the webview's readable "Share Data" file. This script polls those files and downloads
every new article of the target account: text, original HTML, and all images.

  python watch_corpus.py --biz "Mzg3NDkwNzA2OA==" --out "D:\wx_corpus\some-account"
  python watch_corpus.py --biz "..." --out "..." --once        # single sweep, then exit
  python watch_corpus.py --biz "..." --out "..." --retry-failed

Stop with Ctrl-C. Re-running skips anything already downloaded.
"""
from __future__ import annotations
import argparse, glob, html as _html, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 MicroMessenger/7.0.20")
URL_RE = re.compile(rb"https://mp\.weixin\.qq\.com/s\?[^\x00-\x20\"'<>]{40,}")


# ---------- Share Data ----------
def wechat_dirs():
    appdata = os.environ.get("APPDATA", "")
    return [p for p in (os.path.join(appdata, "Tencent", "xwechat", "radium"),
                        os.path.join(appdata, "Tencent", "xwechat"),
                        os.path.join(appdata, "Tencent", "WeChat")) if os.path.isdir(p)]


def find_share_data():
    out = []
    for root in wechat_dirs():
        for pat in ("web/profiles/*/Share Data", "profiles/*/Share Data",
                    "web/profiles/*/*/Share Data", "**/Share Data"):
            out.extend(glob.glob(os.path.join(root, pat), recursive=True))
    seen, uniq = set(), []
    for p in sorted(set(out), key=lambda p: -os.path.getmtime(p)):
        rp = os.path.realpath(p)
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return uniq


def url_clean(s):
    out = []
    for ch in s:
        if ord(ch) < 33 or ord(ch) > 126:
            break
        out.append(ch)
    return "".join(out).rstrip("&")


VOLATILE = {"key", "uin", "pass_ticket", "exportkey", "sessionid", "session_us",
            "wxtoken", "ascene", "acctmode", "devicetype", "version", "lang",
            "countrycode", "wx_header", "clicktime", "enterid", "click_id",
            "scene", "subscene", "exptype", "ranksessionid", "req_id", "from_xworker",
            "fasttmpl_type", "fasttmpl_fullversion", "new"}


def canonical_url(url):
    """Drop session/volatile params so a stored link is just the article identity."""
    try:
        pr = urllib.parse.urlparse(url)
        q = urllib.parse.parse_qsl(pr.query, keep_blank_values=True)
        keep = [(k, v) for k, v in q if k not in VOLATILE]
        return urllib.parse.urlunparse(pr._replace(query=urllib.parse.urlencode(keep),
                                                   fragment=pr.fragment))
    except Exception:
        return url


def scan(biz):
    """{mid: url} for the target account; only URLs carrying chksm are usable."""
    found = {}
    for f in find_share_data():
        try:
            blob = open(f, "rb").read()
        except OSError:
            continue
        for m in URL_RE.finditer(blob):
            u = _html.unescape(url_clean(m.group(0).decode("utf-8", "replace")))
            q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
            if q.get("__biz", [""])[0] != biz:
                continue
            mid = q.get("mid", [""])[0]
            if mid and "chksm" in q:
                found[mid] = u
    return found


# ---------- article fetch/parse ----------
def http_get(url, referer="https://mp.weixin.qq.com/"):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": referer,
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def _first(text, *pats):
    for p in pats:
        m = re.search(p, text, re.S)
        if m:
            return _html.unescape(m.group(1)).strip()
    return ""


def html_to_text(frag):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", frag, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(p|div|section|li|h[1-6]|tr)>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = _html.unescape(s)
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def fetch_article(url):
    page = http_get(url)
    title = _first(page, r'<meta property="og:title" content="([^"]*)"',
                   r"var msg_title = '([^']*)'", r"<title>(.*?)</title>")
    author = _first(page, r'<meta property="og:article:author" content="([^"]*)"',
                    r'<meta name="author" content="([^"]*)"',
                    r"nick_name: '([^']*)'")
    pub = _first(page, r"var ct = \"(\d+)\"", r'"publish_time"\s*:\s*"?(\d+)',
                 r"create_time[\"']?\s*[:=]\s*[\"']?(\d{9,})")
    biz = _first(page, r'var biz = "([^"]+)"', r"__biz=([A-Za-z0-9+/=]+)")
    mid = _first(page, r'var mid = "([^"]+)"', r"mid=(\d+)")
    m = re.search(r'<div[^>]+id="js_content"[^>]*>(.*?)</div>', page, re.S)
    text = html_to_text(m.group(1)) if m else _first(page, r'<meta property="og:description" content="([^"]*)"')
    imgs = []
    scope = m.group(1) if m else page
    for iu in re.findall(r'data-src="([^"]+)"', scope) + re.findall(r'<img[^>]+src="([^"]+)"', scope):
        iu = _html.unescape(iu).replace("\\x26amp;", "&").replace("&amp;", "&")
        if iu.startswith("http") and iu not in imgs:
            imgs.append(iu)
    cover = _first(page, r'<meta property="og:image" content="([^"]*)"')
    url = canonical_url(url)
    return page, {"url": url, "title": title, "author": author, "publish_time": pub,
                  "biz": biz, "mid": mid or "", "text": text, "images": imgs, "cover": cover}


def safe_name(s, n=48):
    s = re.sub(r"[^\w\u4e00-\u9fff\- ]+", "_", s or "")
    return re.sub(r"\s+", " ", s).strip("_ .")[:n].strip("_ .") or "untitled"


def dl_image(url, path):
    try:
        u = _html.unescape(url).replace("\\x26amp;", "&").replace("&amp;", "&")
        u = u.split('"')[0].split("\\")[0]
        req = urllib.request.Request(u, headers={"User-Agent": UA,
                                                 "Referer": "https://mp.weixin.qq.com/"})
        with urllib.request.urlopen(req, timeout=40) as r:
            data = r.read()
        if not data:
            return False
        ct = (r.headers.get("Content-Type") or "").lower()
        ext = ".png" if "png" in ct else (".gif" if "gif" in ct else (".webp" if "webp" in ct else ".jpg"))
        open(path + ext, "wb").write(data)
        return True
    except Exception:
        return False


class Watcher:
    def __init__(self, biz, out, state=None, retry_failed=False):
        self.biz = biz
        self.out = os.path.abspath(out)
        self.state = state or os.path.join(self.out, "_state.json")
        self.retry_failed = retry_failed
        os.makedirs(self.out, exist_ok=True)
        self.st = self._load()

    def _load(self):
        try:
            return json.load(open(self.state, encoding="utf-8"))
        except Exception:
            return {"done": {}}

    def _save(self):
        tmp = self.state + ".tmp"
        json.dump(self.st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, self.state)

    def _log(self, msg):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        try:
            open(os.path.join(self.out, "_watch.log"), "a", encoding="utf-8").write(line + "\n")
        except Exception:
            pass

    def _pending(self, found):
        out = []
        for mid, url in found.items():
            rec = self.st["done"].get(mid)
            if rec is None:
                out.append((mid, url))
            elif self.retry_failed and rec.get("error"):
                out.append((mid, url))
        return out

    def download(self, mid, url):
        page = meta = None
        for _ in range(3):
            try:
                page, meta = fetch_article(url)
                break
            except Exception:
                time.sleep(3)
        if not meta:
            return None
        try:
            date = datetime.fromtimestamp(int(meta.get("publish_time") or 0)).strftime("%Y-%m-%d")
        except Exception:
            date = "0000-00-00"
        folder = os.path.join(self.out, "%s_%s_%s" % (date, safe_name(meta.get("title")), mid))
        os.makedirs(folder, exist_ok=True)
        open(os.path.join(folder, "article.html"), "w", encoding="utf-8").write(page)
        json.dump(meta, open(os.path.join(folder, "meta.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        open(os.path.join(folder, "article.md"), "w", encoding="utf-8").write(
            "# %s\n\n- 公众号: %s (biz=%s)\n- 发布: %s\n- 原始链接: %s\n- 采集时间: %s\n\n---\n\n%s\n"
            % (meta.get("title"), meta.get("author"), meta.get("biz"), date, canonical_url(url),
               datetime.now().strftime("%Y-%m-%d %H:%M"), meta.get("text") or ""))
        imgs = meta.get("images") or []
        saved = 0
        if imgs:
            idir = os.path.join(folder, "images")
            os.makedirs(idir, exist_ok=True)
            for j, iu in enumerate(imgs, 1):
                if dl_image(iu, os.path.join(idir, "%03d" % j)):
                    saved += 1
        return {"title": meta.get("title"), "date": date, "chars": len(meta.get("text") or ""),
                "images": len(imgs), "saved": saved, "folder": folder}

    def run(self, interval=3, once=False, limit=None):
        self._log("watching biz=%s -> %s (have %d)" % (self.biz, self.out, len(self.st["done"])))
        idle = 0
        n_done = 0
        while True:
            try:
                found = scan(self.biz)
            except Exception as e:
                self._log("scan error: %r" % e)
                found = {}
            pend = self._pending(found)
            if limit:
                pend = pend[:max(0, limit - n_done)]
            if pend:
                self._log("new: %d (%s)" % (len(pend), ", ".join(m for m, _ in pend)))
                for mid, url in pend:
                    try:
                        rec = self.download(mid, url)
                    except Exception as e:
                        rec = None
                        self._log("  error %s: %r" % (mid, e))
                    if rec:
                        self.st["done"][mid] = rec
                        n_done += 1
                        self._log("  ok %s | %s | %d chars, %d/%d imgs"
                                  % (mid, (rec["title"] or "")[:40], rec["chars"], rec["saved"], rec["images"]))
                    else:
                        self.st["done"][mid] = {"error": "fetch"}
                        self._log("  FAILED %s" % mid)
                    self._save()
                idle = 0
            else:
                idle += 1
                if idle % 20 == 0:
                    self._log("idle… archived %d" % len(self.st["done"]))
            if once:
                break
            if limit and n_done >= limit:
                break
            time.sleep(interval)
        self._log("stopped; archived %d" % len(self.st["done"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Archive WeChat official-account articles as the user opens them.")
    ap.add_argument("--biz", required=True, help="target account's __biz (get it from probe_env.py --url)")
    ap.add_argument("--out", required=True, help="corpus directory")
    ap.add_argument("--state", help="state file (default: <out>/_state.json)")
    ap.add_argument("--interval", type=float, default=3.0, help="poll interval in seconds (>=2 recommended)")
    ap.add_argument("--once", action="store_true", help="single sweep then exit")
    ap.add_argument("--limit", type=int, help="stop after archiving N new articles")
    ap.add_argument("--retry-failed", action="store_true", help="retry entries previously marked as failed")
    a = ap.parse_args(argv)
    if a.interval < 1:
        print("note: interval <1s gives no benefit; using 2s", file=sys.stderr)
        a.interval = 2.0
    Watcher(a.biz, a.out, a.state, a.retry_failed).run(a.interval, a.once, a.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
