# Share Data 文件：位置、格式与字段

## 位置

```
%APPDATA%\Tencent\xwechat\radium\web\profiles\multitab_<32位hex>\Share Data
```

- 一般是**多个** profile 目录（对应不同登录过的微信账号）
- 目录名的前 4 位 hex 对应 `D:\WeChatFile\xwechat_files\wxid_*_<4位>` 的后缀
- 这个文件**不加锁、可直接读**（同目录的 `Network\Cookies` 是独占锁，读不到，别浪费时间）
- 它是**二进制容器 + 明文文本**，用 `rb` 读再 `decode("utf-8","replace")` 即可

## 里面有什么

主要是**微信 webview 打开过的 URL**，包括：

| 形态 | 说明 |
|---|---|
| `https://mp.weixin.qq.com/s/<sn>` | 文章的**短链**（无 __biz，需要跟一次重定向） |
| `https://mp.weixin.qq.com/s?__biz=..&mid=..&idx=1&sn=..&chksm=..&scene=126&...&key=..` | 文章的**完整链**（★ 这个能直接抓正文） |
| `https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=..&scene=124&uin=..&key=..` | 公众号**历史页**（★ 本文档只用来审计，不用于列表） |
| `weixin://resourceid/Search/app.html?query=...` | 微信内部搜索深链 |

同一文件里会混着**很多公众号**的文章。按 `__biz` 过滤即可。

## 正文 URL 的关键字段

| 字段 | 含义 | 备注 |
|---|---|---|
| `__biz` | 公众号唯一 ID（base64） | 用来锁定目标号 |
| `mid` | 该文章的消息 ID | **去重键** |
| `idx` | 同一次推送里的第几篇（通常 1） | |
| `sn` | 文章随机标识 | **必需**，无法推导 |
| `chksm` | 访问签名 | **必需**，且**每次访问都会变**（同一篇 `mid` 在不同时刻值不同） |
| `scene` / `subscene` | 进入来源 | 与抓正文无关 |
| `key` / `uin` / `pass_ticket` | 微信会话凭据 | 抓**正文**用不到；只有 `profile_ext` 才需要，且与 biz 绑定 |

**判据**：一条 URL 只要同时带 `__biz`、`mid`、`chksm`，就能直接 GET 到完整正文
（普通浏览器 UA 即可，不需要登录态、不需要 cookie）。

## 怎么拿到目标号的 `__biz`

1. 让用户给一篇该号文章链接（`https://mp.weixin.qq.com/s/<sn>` 短链也行）
2. 拉一次那个页面，取：
   - `var biz = "Mzg3NDkwNzA2OA=="` → `__biz`
   - `<meta name="author" content="...">` 或 `nick_name: '...'` → 公众号显示名

`probe_env.py --url <链接>` 已经实现了这一步。

## 会话 key 的时效（只有用到 profile_ext 时才有意义）

- key 从"微信 webview 打开某个 mp.weixin.qq.com 页面"时写入
- 生命周期约**几十分钟**；过期后 `profile_ext` 返回 `ret=-3 no session`
- 同一个 `Share Data` 里的多条 URL **共用最后一次**写入的 key
- 但 key 与 `__biz` **绑定**：拿 A 号的 key 去请求 B 号的 `profile_ext`，会返回验证页

> 本技能**不需要** key —— 抓正文只用文章 URL 里的 `sn`+`chksm`。

## 安全性

- 这些文件是微信自己写给 webview 的可读缓存，**读取不会影响微信运行**
- 不要复制 `Network\Cookies`（独占锁，且没必要）
- 不要注入微信进程；本技能只用文件读取 + 普通 HTTP GET
