#!/usr/bin/env python3
"""Probe the local WeChat PC client: readable Share Data files, WeChat processes,
and which official accounts (by __biz) already appear in the cache.

Usage:
  python probe_env.py                    # inventory
  python probe_env.py --url <article url>  # resolve that article's __biz (and the account name)
"""
from __future__ import annotations
import argparse, glob, html, os, re, sys, urllib.parse, urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

URL_RE = re.compile(rb"https://mp\.weixin\.qq\.com/s\?[^\x00-\x20\"'<>]{40,}")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 MicroMessenger/7.0.20")


def wechat_dirs():
    appdata = os.environ.get("APPDATA", "")
    cands = [
        os.path.join(appdata, "Tencent", "xwechat", "radium"),
        os.path.join(appdata, "Tencent", "xwechat"),
        os.path.join(appdata, "Tencent", "WeChat"),
    ]
    return [p for p in cands if os.path.isdir(p)]


def find_share_data():
    """All existing 'Share Data' files, newest first (may list duplicates for the same file)."""
    out = []
    for root in wechat_dirs():
        for pat in ("web/profiles/*/Share Data", "profiles/*/Share Data",
                    "web/profiles/*/*/Share Data", "**/Share Data"):
            out.extend(glob.glob(os.path.join(root, pat), recursive=True))
    seen, uniq = set(), []
    for p in sorted(set(out), key=lambda p: -os.path.getmtime(p)):
        rp = os.path.realpath(p)
        if rp in seen:
            continue
        seen.add(rp)
        uniq.append(p)
    return uniq


def url_clean(s: str) -> str:
    out = []
    for ch in s:
        if ord(ch) < 33 or ord(ch) > 126:
            break
        out.append(ch)
    return "".join(out).rstrip("&")


def scan_urls():
    """[(url, biz, mid, idx, has_chksm, share_data_path)]"""
    rows = []
    for f in find_share_data():
        try:
            blob = open(f, "rb").read()
        except OSError:
            continue
        for m in URL_RE.finditer(blob):
            u = html.unescape(url_clean(m.group(0).decode("utf-8", "replace")))
            q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
            biz = q.get("__biz", [""])[0]
            if not biz:
                continue
            rows.append({
                "url": u, "biz": biz, "mid": q.get("mid", [""])[0],
                "idx": q.get("idx", [""])[0],
                "has_chksm": "chksm" in q, "file": f,
            })
    return rows


def resolve_biz_from_url(url: str):
    """Return (biz, nickname, sample_full_url). Accepts a /s/<sn> short link or a full /s?... URL."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    biz = q.get("__biz", [""])[0]
    if biz:
        return biz, "", url
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=40) as r:
        page = r.read().decode("utf-8", "replace")
    m = re.search(r'var biz = "([^"]+)"', page) or re.search(r"__biz=([A-Za-z0-9+/=]+)", page)
    biz = m.group(1) if m else ""
    n = re.search(r"<meta name=\"author\" content=\"([^\"]*)\"", page) or \
        re.search(r"nick_name: '([^']*)'", page)
    return biz, (html.unescape(n.group(1)) if n else ""), url


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="an mp.weixin.qq.com article URL to resolve")
    args = ap.parse_args(argv)

    sd = find_share_data()
    print("## WeChat install dirs")
    for d in wechat_dirs():
        print("  ", d)
    print("## readable 'Share Data' files: %d" % len(sd))
    for f in sd:
        try:
            open(f, "rb").close()
            ok = "readable"
        except OSError:
            ok = "LOCKED"
        print("   %-8s %9d  %s" % (ok, os.path.getsize(f), os.path.normpath(f)))

    print("## WeChat processes")
    try:
        import subprocess
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Weixin.exe", "/FO", "CSV"],
                             capture_output=True, text=True, timeout=20).stdout
        print("  ", out.strip().replace("\r\n", "\n   ") or "(none)")
    except Exception as e:
        print("   (tasklist failed: %r)" % e)

    rows = scan_urls()
    print("## articles found in Share Data: %d" % len(rows))
    by_biz = {}
    for r in rows:
        by_biz.setdefault(r["biz"], []).append(r)
    for biz, items in sorted(by_biz.items(), key=lambda kv: -len(kv[1]))[:15]:
        with_chk = [i for i in items if i["has_chksm"]]
        print("   %-24s %3d article(s), %d downloadable" % (biz, len(items), len(with_chk)))

    if args.url:
        print("## resolving --url")
        try:
            biz, nick, sample = resolve_biz_from_url(args.url)
            print("   biz      :", biz)
            print("   nickname :", nick or "(not resolved)")
            n = len(by_biz.get(biz, []))
            print("   already in Share Data:", n)
            if n:
                print("   sample   :", by_biz[biz][0]["url"][:140])
        except Exception as e:
            print("   ERR %r" % e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
