#!/usr/bin/env python3
"""wx2md — 把微信公众号文章链接转成 Markdown。零依赖，只用 Python 标准库。

用法:
  python3 wx2md.py <文章链接> [<链接2> ...]       # 输出到当前目录 <标题>.md
  python3 wx2md.py <链接> -                       # 直接打印到终端
  python3 wx2md.py <链接> -o 目录 --images        # 指定目录，并把图片下载到本地

支持普通图文文章，也支持"图片消息"（小绿书）。
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def fetch(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def js_unescape(s):
    """解码 JS 字符串里的 \\x0a、\\u4e2d、\\' 之类转义，以及 &amp; 等 HTML 实体。"""
    s = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r"\\(.)", r"\1", s)
    return html.unescape(html.unescape(s))


def first(pattern, text, default=""):
    m = re.search(pattern, text, re.S)
    return js_unescape(m.group(1)).strip() if m else default


class MD(HTMLParser):
    """把 #js_content 里的 HTML 转成 Markdown（够用版）。"""
    BLOCK = {"p", "div", "section", "blockquote", "li", "h1", "h2", "h3",
             "h4", "h5", "h6", "pre", "tr", "figure", "figcaption", "ul", "ol"}
    SKIP = {"script", "style", "svg", "mpvoice", "mpvideo", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.inside = 0      # 进入 js_content 后的 div 深度
        self.skip = 0
        self.pre = 0
        self.lists = []      # 栈: ["ul"|"ol", 计数]
        self.quote = 0
        self.href = None
        self.images = []
        self.rows, self.row, self.saved = [], [], None

    def nl(self, n=2):
        self.out.append("\n" * n)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if not self.inside:
            if tag == "div" and a.get("id") == "js_content":
                self.inside = 1
            return
        if tag == "div":
            self.inside += 1
        if self.skip or tag in self.SKIP:
            if tag in self.SKIP:
                self.skip += 1
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.nl(); self.out.append("#" * int(tag[1]) + " ")
        elif tag in ("p", "section", "figure", "tr"):
            self.nl(1)
        elif tag == "br":
            self.out.append("  \n")
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("*")
        elif tag == "blockquote":
            self.quote += 1; self.nl()
        elif tag in ("ul", "ol"):
            self.lists.append([tag, 0]); self.nl(1)
        elif tag == "li":
            self.nl(1)
            kind = self.lists[-1] if self.lists else ["ul", 0]
            kind[1] += 1
            indent = "  " * max(len(self.lists) - 1, 0)
            self.out.append(indent + ("%d. " % kind[1] if kind[0] == "ol" else "- "))
        elif tag == "pre":
            self.pre += 1; self.nl(); self.out.append("```\n")
        elif tag == "code" and not self.pre:
            self.out.append("`")
        elif tag == "a":
            self.href = a.get("href")
            if self.href:
                self.out.append("[")
        elif tag == "img":
            src = a.get("data-src") or a.get("src") or ""
            if src.startswith("http"):
                self.images.append(src)
                self.nl(1); self.out.append("![](%s)" % src); self.nl(1)
        elif tag == "table":
            self.rows = []; self.nl()
        elif tag in ("td", "th"):
            self.saved, self.out = self.out, []   # 单元格内容先单独收集

    def end_cell(self):
        cell = re.sub(r"\s+", " ", "".join(self.out)).strip().replace("|", "\\|")
        self.out = self.saved
        self.saved = None
        self.row.append(cell)

    def handle_endtag(self, tag):
        if not self.inside:
            return
        if tag in self.SKIP and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag == "div":
            self.inside -= 1
        if tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("*")
        elif tag == "blockquote":
            self.quote -= 1; self.nl()
        elif tag in ("ul", "ol") and self.lists:
            self.lists.pop(); self.nl(1)
        elif tag == "pre":
            self.pre -= 1; self.out.append("\n```"); self.nl()
        elif tag == "code" and not self.pre:
            self.out.append("`")
        elif tag == "a" and self.href:
            self.out.append("](%s)" % self.href); self.href = None
        elif tag in ("td", "th") and self.saved is not None:
            self.end_cell()
        elif tag == "tr":
            if self.row:
                self.rows.append(self.row)
            self.row = []
        elif tag == "table":
            if self.rows:
                w = max(len(r) for r in self.rows)
                rows = [r + [""] * (w - len(r)) for r in self.rows]
                lines = ["| " + " | ".join(r) + " |" for r in rows]
                lines.insert(1, "|" + " --- |" * w)
                self.out.append("\n".join(lines))
            self.rows = []; self.nl()
        elif tag in self.BLOCK:
            self.nl(1 if tag in ("li", "tr") else 2)

    def handle_data(self, data):
        if not self.inside or self.skip:
            return
        if not self.pre:
            data = re.sub(r"\s+", " ", data.replace(" ", " "))
        if self.quote and self.out and self.out[-1].endswith("\n"):
            data = "> " + data.lstrip()
        self.out.append(data)

    def markdown(self):
        text = "".join(self.out)
        text = re.sub(r"\*\*\s*\*\*", "", text)          # 空的加粗
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def convert(url):
    page = fetch(url)
    if "js_content" not in page and "content_noencode" not in page:
        hint = first(r'<div class="weui-msg__desc">(.*?)</div>', page) or \
               first(r'<p class="weui-msg__title">(.*?)</p>', page)
        raise RuntimeError("拿不到正文：%s" % (hint or "页面可能需要验证或已被删除"))

    title = first(r'<meta property="og:title" content="(.*?)"', page) or \
        first(r"var msg_title = '(.*?)'", page)
    account = first(r"nick_name: '(.*?)'", page) or first(r'var nickname = "(.*?)"', page)
    author = first(r"author: '(.*?)'", page)
    # 页面里直接给了北京时间的字符串，优先用它，避免本机时区不同导致偏差
    date = first(r"create_time: '(\d{4}-\d\d-\d\d \d\d:\d\d)'", page)
    if not date:
        ts = first(r"create_time: '(\d+)'", page)
        date = time.strftime("%Y-%m-%d %H:%M", time.gmtime(int(ts) + 8 * 3600)) if ts else ""

    body, images = "", []
    if 'id="js_content"' in page:
        p = MD()
        p.feed(page)
        body, images = p.markdown(), p.images
    if not body:  # 图片消息 / 纯文字分享
        text = first(r"content_noencode: '(.*?)',\s*\n", page)
        pics = [js_unescape(u) for u in re.findall(
            r"cdn_url: '([^']+)',\s*width:", page)]
        images = list(dict.fromkeys(pics))
        body = text.replace("\n", "  \n").replace("  \n  \n", "\n\n")
        body += "\n\n" + "\n\n".join("![](%s)" % u for u in images)

    meta = " · ".join(x for x in (account, author if author != account else "", date) if x)
    md = "# %s\n\n> %s  \n> 原文：%s\n\n%s\n" % (title, meta, url, body.strip())
    return title, md, images


def safe(name):
    return re.sub(r'[\\/:*?"<>|\n\r\t]', "_", name).strip()[:80] or "article"


def main():
    ap = argparse.ArgumentParser(description="微信公众号文章 → Markdown（零依赖）")
    ap.add_argument("urls", nargs="+", help="文章链接；最后加一个 - 表示打印到终端")
    ap.add_argument("-o", "--outdir", default=".", help="输出目录（默认当前目录）")
    ap.add_argument("--images", action="store_true", help="把图片下载到本地")
    args = ap.parse_args()

    to_stdout = args.urls[-1] == "-"
    urls = [u for u in args.urls if u != "-"]
    failed = 0
    for url in urls:
        try:
            title, md, images = convert(url)
        except Exception as e:  # noqa
            failed += 1
            print("✗ %s\n  %s" % (url, e), file=sys.stderr)
            continue
        if to_stdout:
            print(md)
            continue
        os.makedirs(args.outdir, exist_ok=True)
        name = safe(title)
        if args.images and images:
            imgdir = os.path.join(args.outdir, name + "_images")
            os.makedirs(imgdir, exist_ok=True)
            for i, u in enumerate(images, 1):
                ext = (re.search(r"wx_fmt=(\w+)", u) or re.search(r"(png|gif|jpe?g|webp)", u))
                fn = "%02d.%s" % (i, ext.group(1) if ext else "jpg")
                try:
                    with open(os.path.join(imgdir, fn), "wb") as f:
                        f.write(fetch(u, binary=True))
                    # 用 <...> 包住路径，标题里有空格也能正常显示
                    md = md.replace("(%s)" % u, "(<%s/%s>)" % (name + "_images", fn))
                except Exception as e:  # noqa
                    print("  图片下载失败 %s: %s" % (u, e), file=sys.stderr)
        path = os.path.join(args.outdir, name + ".md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        print("✓ %s  (%d 字, %d 图)" % (path, len(md), len(images)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
