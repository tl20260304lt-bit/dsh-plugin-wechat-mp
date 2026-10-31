# 正文图片与 OCR 的边界

## 为什么要读这里

图片分享型短文（`window.item_show_type = '8'`，页面 class `page_share_img`）的正文
是 1~N 张 `mmbiz.qpic.cn` 图片，`#js_content` 不存在。此时：

- 正文文字只有一句摘要（在 `js_image_content` 里，脚本已提取到 `text`）。
- 图片本身**不能直接交给模型看**（当前模型不支持图像输入，`view_image` 会被拒绝）。
- 要拿到图内文字只能走 OCR。

## Windows 内置 OCR（已实测可用）

```powershell
# 必须用 Windows PowerShell 5.1；PS7 下 WinRT 类型投影不可用
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File scripts\win_ocr.ps1 -Path <图片路径> -Lang zh-Hans-CN
```

可用语言检测：

```powershell
powershell.exe -NoProfile -Command "$null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]; [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | % LanguageTag"
```

本次实测环境：`zh-Hans-CN` 可用，识别一段中文测试图基本正确（有若干形近字错误，如
"阻"→"阝且"）。

## 提高识别率的做法

1. 先放大 2×（LANCZOS）再 OCR。
2. 长截图切成 4~6 条横条分别 OCR，再拼接。
3. 优先 OCR 页面截图/含大字号标题的图。

## 现实预期

- 立创EDA/KiCad 等 EDA 截图，网表/标号字号极小，OCR 常常只能识别出水印（"公众号·XXX"）。
  **不要依据这类 OCR 结果做工程结论。**
- 若正文 HTML 存在（普通图文），永远优先用 HTML 文本，不要用 OCR。

## 抓图的顺序建议

1. `python wx_mp.py article <url>` → 拿 `images[]`。
2. `curl -sL -A "<desktop UA>" -e "https://mp.weixin.qq.com/" -o art_N.jpg "<url>"` 下载。
3. 放大/切条 → `win_ocr.ps1`。
4. 把 OCR 结果标注为"OCR 提取，可能有误"，不与 HTML 文本混用。
