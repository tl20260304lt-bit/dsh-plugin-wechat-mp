#!/usr/bin/env python3
r"""Build _index.csv and README.md for a corpus produced by watch_corpus.py.

  python build_index.py --corpus "D:\wx_corpus\some-account"
"""
from __future__ import annotations
import argparse, csv, json, os, re, sys, urllib.parse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VOLATILE = {"key","uin","pass_ticket","exportkey","sessionid","session_us","wxtoken",
            "ascene","acctmode","devicetype","version","lang","countrycode","wx_header",
            "clicktime","enterid","click_id","scene","subscene","exptype","ranksessionid",
            "req_id","from_xworker","fasttmpl_type","fasttmpl_fullversion","new"}


def canonical(url):
    try:
        pr = urllib.parse.urlparse(url)
        q = [(k, v) for k, v in urllib.parse.parse_qsl(pr.query, keep_blank_values=True)
             if k not in VOLATILE]
        return urllib.parse.urlunparse(pr._replace(query=urllib.parse.urlencode(q)))
    except Exception:
        return url


FOLDER_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.*)_(\d+)$")


def read_article(folder):
    """Return (title, date, mid, chars, images, url) for one article folder."""
    meta = {}
    mp = os.path.join(folder, "meta.json")
    if os.path.exists(mp):
        try:
            meta = json.load(open(mp, encoding="utf-8"))
        except Exception:
            meta = {}
    md = os.path.join(folder, "article.md")
    text = ""
    if os.path.exists(md):
        try:
            text = open(md, encoding="utf-8").read()
        except Exception:
            text = ""
    body = text.split("---", 1)[-1] if text else ""
    body_chars = len(re.sub(r"\s+", "", body))
    idir = os.path.join(folder, "images")
    images = len([f for f in os.listdir(idir) if os.path.isfile(os.path.join(idir, f))]) \
        if os.path.isdir(idir) else 0
    url = meta.get("url") or ""
    if not url:
        mu = re.search(r"原始链接:\s*(\S+)", text)
        url = mu.group(1) if mu else ""
    return (meta.get("title") or "", body_chars, images, canonical(url))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--title", default="", help="corpus title for README")
    a = ap.parse_args(argv)

    base = os.path.abspath(a.corpus)
    rows = []
    for name in sorted(os.listdir(base)):
        p = os.path.join(base, name)
        if not os.path.isdir(p) or name.startswith("_") or name.startswith("."):
            continue
        m = FOLDER_RE.match(name)
        date = m.group(1) if m else ""
        mid = m.group(3) if m else ""
        title, chars, images, url = read_article(p)
        if not title:
            title = m.group(2) if m else name
        rows.append({"date": date, "title": title, "mid": mid, "chars": chars,
                     "images": images, "url": url, "folder": name})
    rows.sort(key=lambda r: (r["date"], r["mid"]))

    csv_path = os.path.join(base, "_index.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["date", "title", "mid", "chars", "images", "url", "folder"])
        w.writeheader()
        w.writerows(rows)

    if rows:
        readme = ("# %s\n\n"
                  "文章数：%d　｜　正文合计：约 %s 字　｜　配图：%d 张\n"
                  "时间跨度：%s → %s\n\n"
                  "## 目录结构\n\n```\n"
                  "_index.csv      全库索引（日期/标题/mid/字数/图片数/链接）★从这看\n"
                  "<日期>_<标题>_<mid>/\n"
                  "  article.md      正文（Markdown）\n"
                  "  article.html    原始页面（离线留档）\n"
                  "  meta.json       元数据\n"
                  "  images/...      全部配图\n```\n\n"
                  "## 用法\n\n"
                  "- 按时间通读 → 文件夹名已按 `YYYY-MM-DD` 前缀排序\n"
                  "- 按主题找 → 打开 `_index.csv`，筛标题关键字\n"
                  "- 要引用 → `meta.json` 里有原始链接和发布时间\n\n"
                  "仅供个人研读，勿再分发。\n"
                  % (a.title or "微信文章库", len(rows), format(sum(r["chars"] for r in rows), ","),
                     sum(r["images"] for r in rows), rows[0]["date"], rows[-1]["date"]))
        open(os.path.join(base, "README.md"), "w", encoding="utf-8").write(readme)

    print("articles: %d" % len(rows))
    if rows:
        print("date range: %s -> %s" % (rows[0]["date"], rows[-1]["date"]))
        print("body chars: %d   images: %d" % (sum(r["chars"] for r in rows),
                                               sum(r["images"] for r in rows)))
    print("index -> %s" % csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
