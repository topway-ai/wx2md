# wx2md

把微信公众号文章链接转成 Markdown。**零依赖**：只用 Python 标准库，不用装包，也不用开浏览器。

- 支持普通图文文章，也支持"图片消息"（小绿书）
- 保留标题、加粗、列表、引用、代码块、链接、表格、图片
- 可选把图片下载到本地
- macOS / Linux 通用，需要 Python 3.7+

## 用法

```bash
# 输出到当前目录 <标题>.md
python3 wx2md.py https://mp.weixin.qq.com/s/xxxx

# 指定目录，并把图片下载到本地
python3 wx2md.py https://mp.weixin.qq.com/s/xxxx -o articles --images

# 一次转多篇
python3 wx2md.py <链接1> <链接2> <链接3> -o articles

# 直接打印到终端
python3 wx2md.py https://mp.weixin.qq.com/s/xxxx -
```

装成系统命令：

```bash
chmod +x wx2md.py && sudo mv wx2md.py /usr/local/bin/wx2md
```

## 原理

公开文章的页面直接用 HTTP 请求就能拿到，正文在 `#js_content` 里；图片消息的正文在页面 JS 变量
`content_noencode` 里，图片在 `picture_page_info_list` 里。工具把这些提取出来，转成 Markdown。

## 限制

- 只能转你手上有链接的公开文章，不能列出一个号的全部历史文章
- 请求太频繁，或者服务器在海外，可能被微信要求验证；这时工具会报"拿不到正文"
- 极简容器里中文显示乱码时，先 `export LANG=C.UTF-8`
- 文章版权归原作者所有，请仅作个人阅读和存档
