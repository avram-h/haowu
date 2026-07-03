#!/usr/bin/env python3
"""
社交媒体自动化发布调度器
- 内容库管理（预写帖子，自动轮转）
- 多平台适配（小红书、微博、Twitter/X、微信公众号）
- 最佳发布时间自动计算
- 半自动发布（生成内容 → 复制粘贴 / API 自动推送）

用法:
  python scheduler.py add       # 添加新内容
  python scheduler.py generate  # 生成今日待发布内容
  python scheduler.py post      # 自动发布（需配置 API）
  python scheduler.py stats     # 查看统计
"""

import json
import os
import random
import hashlib
import time
import base64
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode

BASE_DIR = Path(__file__).parent
CONTENT_BANK = BASE_DIR / "content_bank" / "posts.json"
QUEUE_FILE = BASE_DIR / "content_bank" / "queue.json"
CONFIG_FILE = BASE_DIR / "config.json"
STATS_FILE = BASE_DIR / "content_bank" / "stats.json"

# ============================================================
# 默认配置
# ============================================================

DEFAULT_CONFIG = {
    "platforms": {
        "twitter": {
            "enabled": False,
            "api_key": "",
            "api_secret": "",
            "access_token": "",
            "access_secret": "",
            "bearer_token": ""
        },
        "weibo": {
            "enabled": False,
            "app_key": "",
            "app_secret": "",
            "redirect_uri": "",
            "access_token": ""
        },
        "xiaohongshu": {
            "enabled": False,
            "note": "小红书目前无公开API，建议手动发布"
        },
        "wechat_mp": {
            "enabled": False,
            "appid": "",
            "appsecret": ""
        }
    },
    "schedule": {
        "posts_per_day": 3,
        "best_times": ["08:00", "12:30", "20:00"],
        "timezone": "Asia/Shanghai"
    },
    "content_types": ["好物推荐", "干货分享", "互动话题", "热点资讯", "促销信息"],
    "hashtags": {
        "default": ["好物推荐", "好物分享", "生活好物"],
        "digital": ["数码测评", "数码好物", "科技生活"],
        "home": ["家居好物", "居家必备", "品质生活"],
        "beauty": ["护肤推荐", "男士护肤", "护肤好物"]
    }
}


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            for key in merged:
                if key in cfg:
                    if isinstance(merged[key], dict):
                        merged[key].update(cfg[key])
                    else:
                        merged[key] = cfg[key]
            return merged
    return DEFAULT_CONFIG


def load_content_bank():
    if CONTENT_BANK.exists():
        with open(CONTENT_BANK, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"posts": []}


def save_content_bank(data):
    with open(CONTENT_BANK, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_queue():
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_queue(queue):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def load_stats():
    if STATS_FILE.exists():
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"total_posts": 0, "platform_stats": {}, "history": []}


def save_stats(stats):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


# ============================================================
# 内容管理
# ============================================================

class ContentManager:
    def __init__(self, config):
        self.config = config
        self.bank = load_content_bank()

    def add_post(self):
        """交互式添加新内容"""
        print("\n📝 添加新内容\n" + "=" * 40)

        content_type = self._select("内容类型", self.config["content_types"])
        category = self._select("分类", list(self.config["hashtags"].keys()))

        title = input("标题 (可选): ").strip()
        body = input("正文内容: ").strip()

        if not body:
            print("❌ 内容不能为空")
            return

        link = input("链接 (可选): ").strip()

        # 自动生成各平台适配版本
        hashtags = self.config["hashtags"].get(category, self.config["hashtags"]["default"])
        hashtag_str = " ".join(f"#{t}" for t in hashtags[:3])

        post = {
            "id": hashlib.md5(f"{body}{time.time()}".encode()).hexdigest()[:8],
            "type": content_type,
            "category": category,
            "title": title,
            "body": body,
            "link": link,
            "hashtags": hashtags,
            "created_at": datetime.now().isoformat(),
            "used_count": 0,
            "last_used": None,
            "platforms": {
                "twitter": self._format_for_twitter(body, link, hashtag_str),
                "weibo": self._format_for_weibo(body, link, hashtag_str),
                "xiaohongshu": self._format_for_xiaohongshu(title, body, hashtags, category),
                "wechat_mp": self._format_for_wechat(title, body),
            }
        }

        self.bank["posts"].append(post)
        save_content_bank(self.bank)
        print(f"\n✅ 已添加 (ID: {post['id']})")
        self._preview(post)

    def _select(self, prompt, options):
        print(f"\n{prompt}:")
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        choice = input("选择序号: ").strip()
        try:
            return options[int(choice) - 1]
        except (ValueError, IndexError):
            return options[0]

    def _format_for_twitter(self, body, link, hashtags):
        """Twitter/X 格式（280字限制，适合短平快）"""
        max_len = 260
        hashtags_short = " ".join(hashtags.split()[:2])
        base = f"{body[:150]}\n\n{hashtags_short}"
        if link:
            suffix = f"\n🔗 {link}"
            if len(base) + len(suffix) <= max_len:
                return base + suffix
            return base[:max_len - len(suffix)] + suffix
        return base[:280]

    def _format_for_weibo(self, body, link, hashtags):
        """微博格式（含话题标签）"""
        tags_formatted = " ".join(f"#{t}#" for t in self.config["hashtags"]["default"][:3])
        post = f"{body}\n\n{tags_formatted}"
        if link:
            post += f"\n{link}"
        return post

    def _format_for_xiaohongshu(self, title, body, hashtags, category):
        """小红书格式（标题+正文+标签+分类）"""
        title_line = f"📌 {title}" if title else ""
        tags = " ".join(f"#{t}" for t in hashtags)

        return {
            "title": title_line or body[:20],
            "body": body,
            "tags": tags,
            "category": category,
            "note": "建议配图3-6张，首图加文字标题效果更好"
        }

    def _format_for_wechat(self, title, body):
        """微信公众号文章摘要"""
        return {
            "title": title or "好物推荐",
            "summary": body[:120] + "...",
            "body": body,
            "note": "建议在公众号后台使用富文本编辑器排版"
        }

    def _preview(self, post):
        """预览各平台版本"""
        print("\n📱 各平台预览:")
        print("-" * 40)
        for platform, content in post["platforms"].items():
            print(f"\n🔹 {platform.upper()}:")
            if isinstance(content, dict):
                for k, v in content.items():
                    print(f"  {k}: {v}")
            else:
                print(f"  {content}")
        print("-" * 40)

    def list_posts(self):
        """列出所有内容"""
        if not self.bank["posts"]:
            print("\n📭 内容库为空，请先添加内容")
            return

        print(f"\n📚 内容库 ({len(self.bank['posts'])} 条)")
        print("=" * 50)
        for p in self.bank["posts"]:
            print(f"  [{p['id']}] {p.get('title', p['body'][:40])} | {p['type']} | 已用{p['used_count']}次")


# ============================================================
# 发布调度器
# ============================================================

class PostScheduler:
    def __init__(self, config):
        self.config = config
        self.bank = load_content_bank()
        self.queue = load_queue()

    def generate_today(self, platform=None):
        """生成本日待发布队列"""
        posts_per_day = self.config["schedule"]["posts_per_day"]
        available = [p for p in self.bank["posts"]]

        if not available:
            print("\n📭 内容库为空")
            return

        # 按最少使用次数排序，确保内容均匀轮转
        available.sort(key=lambda p: p["used_count"])

        selected = available[:posts_per_day]
        random.shuffle(selected)

        # 分配到最佳时间
        times = self.config["schedule"]["best_times"][:posts_per_day]
        today = datetime.now().strftime("%Y-%m-%d")

        queue = []
        for i, post in enumerate(selected):
            queue.append({
                "post_id": post["id"],
                "scheduled_time": f"{today} {times[i]}" if i < len(times) else f"{today} 18:00",
                "platform": platform or "all",
                "status": "pending",
                "content": post["body"][:50] + "..."
            })

        save_queue(queue)
        self.queue = queue

        print(f"\n📅 {today} 发布计划")
        print("=" * 50)
        for item in queue:
            post = next((p for p in self.bank["posts"] if p["id"] == item["post_id"]), None)
            if post:
                print(f"  🕐 {item['scheduled_time']}")
                print(f"  📝 {post.get('title', post['body'][:60])}")
                print(f"  🏷️  {' '.join(f'#{t}' for t in post['hashtags'][:3])}")
                print()

        # 生成可复制粘贴的内容文件
        self._export_for_manual_posting(selected, today)

    def _export_for_manual_posting(self, posts, date):
        """导出为手动发布用的文本文件"""
        out_dir = BASE_DIR / "output"
        out_dir.mkdir(exist_ok=True)

        filename = out_dir / f"posts_{date}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"📅 {date} 社交媒体发布内容\n")
            f.write("=" * 50 + "\n\n")

            for i, post in enumerate(posts, 1):
                f.write(f"━━━ 第 {i} 条 ━━━\n\n")
                for platform, content in post["platforms"].items():
                    f.write(f"【{platform.upper()}】\n")
                    if isinstance(content, dict):
                        for k, v in content.items():
                            f.write(f"{v}\n")
                    else:
                        f.write(f"{content}\n")
                    f.write("\n")
                f.write("\n")

        print(f"📄 已导出到: {filename}")

    def post_now(self, platform="all"):
        """立即发布（需要 API 配置）"""
        if not self.queue:
            print("📭 没有待发布内容，请先运行 generate")
            return

        for item in self.queue:
            if item["status"] != "pending":
                continue

            post = next((p for p in self.bank["posts"] if p["id"] == item["post_id"]), None)
            if not post:
                continue

            print(f"\n🚀 发布: {post.get('title', post['body'][:40])}")

            if platform in ("all", "twitter"):
                self._post_to_twitter(post)

            if platform in ("all", "weibo"):
                self._post_to_weibo(post)

            # 更新使用计数
            post["used_count"] = post.get("used_count", 0) + 1
            post["last_used"] = datetime.now().isoformat()
            item["status"] = "posted"
            item["posted_at"] = datetime.now().isoformat()

        save_content_bank(self.bank)
        save_queue(self.queue)

        # 更新统计
        self._update_stats()

    def _post_to_twitter(self, post):
        """发布到 Twitter/X (API v2)"""
        cfg = self.config["platforms"]["twitter"]
        if not cfg["enabled"] or not cfg["bearer_token"]:
            print("  ⚠️ Twitter API 未配置，请手动发布:")
            print(f"  {post['platforms']['twitter']}")
            return

        content = post["platforms"]["twitter"]
        try:
            data = json.dumps({"text": content}).encode()
            req = Request(
                "https://api.twitter.com/2/tweets",
                data=data,
                method="POST"
            )
            req.add_header("Authorization", f"Bearer {cfg['bearer_token']}")
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                print(f"  ✅ Twitter 发布成功: {result.get('data', {}).get('id', '')}")
        except Exception as e:
            print(f"  ❌ Twitter 发布失败: {e}")

    def _post_to_weibo(self, post):
        """发布到微博"""
        cfg = self.config["platforms"]["weibo"]
        if not cfg["enabled"] or not cfg["access_token"]:
            print("  ⚠️ 微博 API 未配置，请手动发布")
            return

        content = post["platforms"]["weibo"]
        try:
            params = urlencode({
                "access_token": cfg["access_token"],
                "status": content.encode("utf-8")
            })
            req = Request(f"https://api.weibo.com/2/statuses/update.json", data=params.encode())
            with urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                print(f"  ✅ 微博发布成功: {result.get('id', '')}")
        except Exception as e:
            print(f"  ❌ 微博发布失败: {e}")

    def _update_stats(self):
        stats = load_stats()
        stats["total_posts"] += sum(1 for q in self.queue if q["status"] == "posted")
        stats["history"].append({
            "date": datetime.now().isoformat(),
            "posts": len([q for q in self.queue if q["status"] == "posted"]),
            "platforms": list(set(
                q["platform"] for q in self.queue if q["status"] == "posted"
            ))
        })
        save_stats(stats)


# ============================================================
# 主程序
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="社交媒体自动化发布调度器")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("add", help="添加新内容到内容库")
    sub.add_parser("list", help="查看所有内容")
    sub.add_parser("generate", help="生成本日发布计划")
    sub.add_parser("post", help="执行发布")
    sub.add_parser("stats", help="查看发布统计")

    args = parser.parse_args()

    # 初始化配置
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        print(f"✅ 配置文件已创建: {CONFIG_FILE}")

    config = load_config()
    manager = ContentManager(config)
    scheduler = PostScheduler(config)

    if args.command == "add":
        manager.add_post()

    elif args.command == "list":
        manager.list_posts()

    elif args.command == "generate":
        scheduler.generate_today()

    elif args.command == "post":
        scheduler.post_now()

    elif args.command == "stats":
        stats = load_stats()
        print(f"\n📊 发布统计")
        print(f"总发布数: {stats['total_posts']}")
        print(f"历史记录: {len(stats['history'])} 天")
        if stats["history"]:
            recent = stats["history"][-5:]
            for h in recent:
                print(f"  {h['date'][:10]}: {h['posts']} 条 → {', '.join(h['platforms'])}")

    else:
        parser.print_help()
        print("\n💡 快速上手:")
        print("  1. python scheduler.py add      # 添加内容")
        print("  2. python scheduler.py generate  # 生成发布计划")
        print("  3. python scheduler.py post      # 执行发布")


if __name__ == "__main__":
    main()
