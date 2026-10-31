# 实测过的死路（别再重复踩）

目标是"拿到某个公众号的**全部**文章列表"。以下路径都在本机实测过，**都不行**，
记录在此以免下次重新验证一遍。

## 1. `mp/profile_ext` 历史消息接口 —— 对部分号恒返回空

会话参数（`uin`/`key`/`pass_ticket`）可从 `Share Data` 读到，用它调：

```
https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=<biz>&scene=124&uin=..&key=..&pass_ticket=..
```

实测结果：

| 情形 | 返回 |
|---|---|
| 用**文章页**上下文拿到的 key | `ret:0 errmsg:ok`，但 `msgList.list = []`、`msg_count = 0` |
| 用**历史页**（profile_ext）上下文拿到的 key | 同样空 |
| 同 key 换别的 `__biz` | 直接返回 2034 字节的验证页（key 与 biz 绑定） |

穷举过 `action=home|getmsg`、`scene=1|124|126|169`、`f=json`、
`count=5|10|20`、`appmsg_token`、`x5=0`、`real_type=43`、`fasttmpl_type` —— **全部 `msg_count=0`**。

**结论**：`profile_ext` 只覆盖"群发"内容。贴图号 / 图片号 / 仅"发布"的号拿不到列表。
微信客户端里能看到的列表，走的是另一条通道（加密协议或本地库），不是这个接口。

## 2. 只靠 `mid` 猜文章 URL

文章页需要 `sn` 与 `chksm`：

- `?__biz=..&mid=..&idx=1` → `参数错误`
- 加正确 `sn` 但不带 `chksm` → 返回壳页面，无正文
- 加正确 `chksm` → **成功**

而 `chksm` 是**每次访问重新生成**的（同一篇 `mid` 在不同时刻的 `chksm` 不同），
无法推导；`sn` 是随机串，也无法猜。**扫 mid 区间不可行。**

## 3. 系统代理 + mitmproxy 抓包

装 mitmproxy、把 CA 证书导入 `CurrentUser\Root`、把系统代理指到 8080 —— 配置全部生效
（浏览器/其它程序都成功被拦截），但：

> **微信 PC 端完全不使用系统 HTTP 代理**，浏览公众号期间抓不到任何一条微信流量。

`Weixin.exe` 走自己的加密协议；webview 也不吃系统代理。除非用**透明模式**
（mitmproxy `--mode local`，Windows 下需要 WinDivert **管理员权限**），否则抓不到。

## 4. 读微信本地数据库

`xwechat_files\<账号>\db_storage\` 下 `biz_message_0.db` 等是 **SQLCipher 4 加密**的
（文件头随机，非 `SQLite format 3`）。密钥不在磁盘上：

- 微信 **4.1.11 之前**：内存里有 `x'<64hex key><32hex salt>'` 字符串，扫内存即可
  （`328336690/wechat-decrypt` 走这条路）——**4.1.11+ 已改掉，实测 0/32 命中**
- 微信 **4.1.11+**：密钥以二进制形式存在于 codec 配置函数的参数中，且还要
  `PBKDF2-HMAC-SHA512, 256000` 派生；只能用 **Frida spawn** 挂钩 `Weixin.dll`
  （函数偏移随小版本漂移，且**有 anti-hook 检测**）
- macOS 版另有明文 `all_keys.json`，**Windows 版没有**

且本地库只存"你收到过的推送"，未必等于"该号的全部文章"。

## 5. 搜狗微信搜索

`https://weixin.sogou.com/weixin?type=2&query=<关键词>` 只能按**关键词**搜，
检索不到"某个号的全部文章"；`type=1`（公众号搜索）对未认证号直接返回
"暂无相关的官方认证订阅号"。且极易触发反爬。覆盖率和时效都很差。

## 6. 文章页里找"合集/专辑"

用过 `appmsgalbum` 接口，但：

- 号必须真的建过合集（文章 HTML 里要有 `album_id`）
- 实测目标号文章里**没有** `album_id`

## 7. 滚一遍历史消息看会不会被缓存

让用户把历史消息滚到底，再扫 `Share Data` / `Local Storage` / `IndexedDB`：
**没有新增**。列表不落在这几个可读位置。

---

## 那么什么能用

**`Share Data` 记录"用户打开过的文章"的完整 URL（含 `sn`+`chksm`），而这个 URL 可以直接抓到正文。**

→ 让用户逐篇点开，脚本盯着 `Share Data` 自动下载。这条路对**任何**号都成立，
是本技能采用的方法。
