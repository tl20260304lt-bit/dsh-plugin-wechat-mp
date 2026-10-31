# 错误码与载荷对照

## appmsg_comment 接口

`GET https://mp.weixin.qq.com/mp/appmsg_comment`

必带参数：

| 参数 | 来源 | 说明 |
|---|---|---|
| `action=getcomment` | 固定 | |
| `appmsgid` | 文章 `mid` | 例 `2247495164` |
| `idx` | 文章 `idx` | 例 `1` |
| `comment_id` | 文章 HTML 内 `cgiData.comment_id` | **必带**，例 `4716661794319302658` |
| `biz` | 文章 `__biz` | base64，例 `MzkxMDIyNzA1MQ==` |
| `uin` / `key` / `pass_ticket` | `Share Data` 里的会话 URL | 有时效 |
| `devicetype` / `version` | 同上 | 例 `UnifiedPCWindows` / `f2541d41` |
| `f=json` `is_need_ad=0` `is_need_ticket=0` `x5=0` `appmsg_token=` | 固定 | |

`Referer` 用**带参数的完整文章 URL**（不是裸 `/s/<sn>`）。

## 返回码

| 返回 | 含义 | 处理 |
|---|---|---|
| `base_resp.ret = 0` | 成功 | 读 `elected_comment` |
| `ret = -2` `invalid args` | 缺/错 `comment_id`、`biz`、`appmsgid` | 用 `article` 重新提取 |
| `ret = -3` `no session`, `cookie_count: 0` | 会话参数缺失或**已过期** | 让用户在微信里重新打开文章，立刻重跑 |

## 成功响应里值得读的字段

| 字段 | 含义 |
|---|---|
| `elected_comment[]` | 公开可见的精选留言 |
| `elected_comment_total_cnt` | 精选留言条数（= `len(elected_comment)`） |
| `total_count` | 文章总评论数（含未精选，**拿不到**） |
| `continue_flag` | `false` 表示已到底；`offset` 参数实际无效 |
| `enabled` | 评论区是否开启 |
| `reply_new.reply_list[]` | 该留言下的回复（含作者回复，`identity_type=0` 为普通用户） |
| 每条留言字段 | `nick_name` `content` `like_num` `create_time` `ip_wording` `content_id` `is_top` |

## 其他接口

| 接口 | 结果 |
|---|---|
| `mp/getappmsgext` | 无会话时只返回空壳（无 `elected_comment`），不要作为评论来源 |
| `mp/appmsg_comment?action=getcomment` 不带 `comment_id` | `ret=-2 invalid args` |
| 页面 HTML 的 `preload_comment_item_list` | 登录态下才有内容，普通抓取为空 |

## 本机路径速查

```
%APPDATA%\Tencent\xwechat\radium\web\profiles\multitab_<hash>\Share Data   # 会话 URL（可读）
%APPDATA%\Tencent\xwechat\radium\web\profiles\multitab_<hash>\Network\Cookies  # 独占锁，放弃
%APPDATA%\Tencent\xwechat\radium\web\profiles\multitab_<hash>\History      # 非 SQLite（加密），放弃
%APPDATA%\Tencent\xwechat\radium\web\Local State                          # os_crypt 密钥（DPAPI）
D:\WeChatFile\xwechat_files\wxid_*_<hash前4位>\                            # 账号数据（无文章/评论缓存）
```

微信客户端进程命令行里的 `--wechat-files-path=` 指向账号数据根目录，可用
`Get-CimInstance Win32_Process -Filter "Name='WeChatAppEx.exe'"` 读取。
