"""B站 API 封装"""

import time
from typing import Optional, List

import httpx


class BilibiliAPI:
    """B站 API 客户端"""

    BASE_URL = "https://api.bilibili.com"
    HISTORY_URL = f"{BASE_URL}/x/web-interface/history/cursor"
    NAV_URL = f"{BASE_URL}/x/web-interface/nav"

    def __init__(self, cookie: str, csrf: str = ""):
        self.cookie = cookie
        self.csrf = csrf
        self.client = httpx.Client(
            headers={
                "Cookie": cookie,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com",
            },
            timeout=15.0,
        )

    def test_connection(self) -> bool:
        """测试 Cookie 是否有效"""
        try:
            resp = self.client.get(self.NAV_URL)
            data = resp.json()
            return data.get("code") == 0
        except Exception:
            return False

    def get_history(
        self,
        max_id: int = 0,
        view_at: int = 0,
        business: str = "archive",
    ) -> tuple:
        """
        获取历史记录

        Args:
            max_id: 上一页的 max 值，用于翻页
            view_at: 上一页的 view_at 值，用于翻页
            business: 业务类型 (archive=视频, live=直播, article=专栏, audio=音频)

        Returns:
            (list, cursor) - 历史记录列表和下一页游标
        """
        params = {
            "max": max_id,
            "view_at": view_at,
            "business": business,
        }

        try:
            resp = self.client.get(self.HISTORY_URL, params=params)
            data = resp.json()

            if data.get("code") != 0:
                raise Exception(f"B站 API 错误: {data.get('message', '未知错误')}")

            result = data.get("data", {})
            history_list = result.get("list", [])
            cursor = result.get("cursor", {})

            return history_list, cursor
        except httpx.HTTPError as e:
            raise Exception(f"请求 B站 API 失败: {e}")

    def fetch_all_history(
        self,
        since_timestamp: int = 0,
        max_pages: int = 50,
        delay: float = 0.5,
    ) -> List[dict]:
        """
        增量拉取所有历史记录

        Args:
            since_timestamp: 起始时间戳（只保留此时间之后的数据）
            max_pages: 最大翻页数
            delay: 每页间隔（秒）

        Returns:
            所有历史记录
        """
        all_items = []
        max_id = 0
        view_at = 0  # 从最新开始

        for page in range(max_pages):
            items, cursor = self.get_history(max_id=max_id, view_at=view_at)
            if not items:
                break

            # 过滤时间范围
            for item in items:
                item_view_at = item.get("view_at", 0)
                if item_view_at >= since_timestamp:
                    all_items.append(item)
                else:
                    # 已经超过时间范围，停止翻页
                    return all_items

            # 使用 cursor 中的值作为下一页的参数
            next_max_id = cursor.get("max", 0)
            next_view_at = cursor.get("view_at", 0)

            # 如果没有更多数据，停止
            if next_max_id == 0 and next_view_at == 0:
                break

            max_id = next_max_id
            view_at = next_view_at

            # 避免请求过快
            time.sleep(delay)

        return all_items

    def close(self):
        self.client.close()
