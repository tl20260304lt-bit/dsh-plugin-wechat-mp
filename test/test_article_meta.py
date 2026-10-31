"""Regression tests for the WeChat article metadata fallback.

Run with: python -m unittest discover -s test -p "test_*.py"
"""

import importlib.util
import pathlib
import unittest

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "assets"
    / "skills"
    / "wechat-mp-content"
    / "scripts"
    / "wx_mp.py"
)

_spec = importlib.util.spec_from_file_location("wx_mp", SCRIPT)
wx_mp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wx_mp)

ARTICLE_URL = (
    "https://mp.weixin.qq.com/s?__biz=MzY4MjQ0Mjc5MQ==&mid=2247484872&idx=1"
    "&sn=8987e5e15ed850628cd863dc106bd655&chksm=f3432c8&key=K&pass_ticket=P&uin=U"
)

# An image-share post: the page carries comment_id but not window.biz / window.mid.
IMAGE_SHARE_HTML = """<html><body><script>
comment_id: '4761001681821990914'
</script></body></html>"""

STANDARD_HTML = """<html><body><script>
window.biz = 'MzU5NjM0MzE4Mw=='
window.mid = '2247543631'
window.idx = 2
window.sn = 'a297e1b150abcd12'
</script></body></html>"""


class ArticleMetaFallbackTest(unittest.TestCase):
    def test_image_share_post_takes_ids_from_the_url(self):
        meta = wx_mp.article_meta(IMAGE_SHARE_HTML, ARTICLE_URL)
        self.assertEqual(meta["biz"], "MzY4MjQ0Mjc5MQ==")
        self.assertEqual(meta["mid"], "2247484872")
        self.assertEqual(meta["idx"], "1")
        self.assertEqual(meta["sn"], "8987e5e15ed850628cd863dc106bd655")
        self.assertEqual(meta["comment_id"], "4761001681821990914")

    def test_page_values_win_over_the_url(self):
        meta = wx_mp.article_meta(STANDARD_HTML, ARTICLE_URL)
        self.assertEqual(meta["biz"], "MzU5NjM0MzE4Mw==")
        self.assertEqual(meta["mid"], "2247543631")
        self.assertEqual(meta["idx"], "2")
        self.assertEqual(meta["sn"], "a297e1b150abcd12")

    def test_missing_ids_and_url_stay_empty(self):
        meta = wx_mp.article_meta("<html></html>", "")
        self.assertEqual(meta["biz"], "")
        self.assertEqual(meta["mid"], "")
        self.assertEqual(meta["idx"], "1")
        self.assertEqual(meta["sn"], "")

    def test_short_link_without_query_is_untouched(self):
        meta = wx_mp.article_meta(IMAGE_SHARE_HTML, "https://mp.weixin.qq.com/s/abcdefghijklmnop")
        self.assertEqual(meta["mid"], "")
        self.assertEqual(meta["idx"], "1")


if __name__ == "__main__":
    unittest.main()
