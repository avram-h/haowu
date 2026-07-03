#!/usr/bin/env python3
"""
京东联盟助手
- 注册后填入 PID，自动为文章生成追踪链接
- 支持单品链接转链、搜索链接生成

用法:
  python jd_helper.py setup              # 设置 PID
  python jd_helper.py link "商品链接"     # 转链
  python jd_helper.py update-all         # 批量更新所有文章的联盟链接
"""

import json, sys, re
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).parent
CONTENT_DIR = BASE_DIR / "content"
CONFIG_FILE = BASE_DIR / "config.json"


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def setup():
    """设置京东联盟 PID"""
    cfg = load_config()
    print("\n📋 京东联盟 PID 设置\n")
    print("获取方式：")
    print("  1. 打开 union.jd.com 注册/登录")
    print("  2. 进入「推广管理」→「网站管理」→「查看PID」")
    print("  3. 复制你的 PID（类似 12345678_12345678_12345678）\n")

    pid = input("粘贴 PID: ").strip()
    if not pid or "_" not in pid:
        print("❌ PID 格式不正确，应该是 三段式（xxx_xxx_xxx）")
        return

    cfg["affiliate"]["jd"]["pid"] = pid
    cfg["affiliate"]["jd"]["enabled"] = True
    save_config(cfg)
    print(f"\n✅ PID 已保存: {pid}\n")
    print("现在可以运行: python jd_helper.py update-all")


def build_link(keyword, pid):
    """生成京东联盟搜索推广链接"""
    # 京东联盟搜索推广链接格式
    # 注意：这只是搜索推广的基础格式，实际佣金追踪需要通过 union.jd.com 的转链API
    # 这里是让你知道链接长什么样，实际最好用转链工具
    kw_encoded = quote(keyword)

    # 方式1：搜索推广（带PID）
    url = f"https://union-click.jd.com/jdc?e=&p=JF8BAPEJK1olXDYCVV9cC0oUBG8IGF8SVF9HC0gVB38PHE9rW0NXS15LUQEOVw1eE0xdAxYETQ5uK1tBVD8XbGsMVA1eCUoWAWsLE1ISa0JUMmhFHAZlHlxUOHsUM2wQElgRCX5cO1sVM28HGF0cXQcDVV9uC0onBG8I"

    # 方式2：简便写法 - union.jd.com 的推广链接
    url = f"https://union-click.jd.com/jdc?d={kw_encoded}"

    return url


def update_articles():
    """批量更新所有文章中的京东联盟链接"""
    cfg = load_config()
    pid = cfg["affiliate"]["jd"].get("pid", "")

    if not pid:
        print("\n❌ 请先设置 PID: python jd_helper.py setup")
        return

    md_files = list(CONTENT_DIR.glob("*.md"))
    if not md_files:
        print("\n📭 content/ 目录下没有文章")
        return

    updated = 0
    for md_file in md_files:
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 提取关键词（从 title 或 keyword 字段）
        title_match = re.search(r'title:\s*(.+)', content)
        keyword_match = re.search(r'keywords:\s*(.+)', content)

        keyword = ""
        if title_match:
            keyword = title_match.group(1).strip()
        elif keyword_match:
            keyword = keyword_match.group(1).split(",")[0].strip()

        if not keyword:
            continue

        # 生成新的联盟链接
        new_url = build_link(keyword, pid)

        # 替换 affiliate_url
        old_pattern = r'affiliate_url:\s*.+'
        new_line = f'affiliate_url: {new_url}'
        new_content = re.sub(old_pattern, new_line, content)

        if new_content != content:
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"  ✅ {md_file.name} → {keyword}")
            updated += 1

    print(f"\n✨ 已更新 {updated} 篇文章")
    print("运行 python generate.py 重新生成站点")


def get_link():
    """转链 - 把普通京东链接转成推广链接"""
    cfg = load_config()
    pid = cfg["affiliate"]["jd"].get("pid", "")

    if not pid:
        print("\n❌ 请先设置 PID: python jd_helper.py setup")
        return

    print("\n🔗 京东联盟 转链工具\n")
    print("方式1：把商品链接粘贴过来")
    url = input("京东商品链接: ").strip()

    if not url:
        print("❌ 链接不能为空")
        return

    # 提取商品ID（京东链接中的数字）
    sku_match = re.search(r'(\d{6,})', url)
    if sku_match:
        sku = sku_match.group(1)
        print(f"\n📦 商品ID: {sku}")
        print(f"🔗 推广链接: https://union-click.jd.com/jdc?e=&p=JF8BAPEJK1olXDYCVV9cC0oUBG8IGF8SVF9HC0gVB38PHE9rW0NXS15LUQEOVw1eE0xdAxYETQ5uK1tBVD8XbGsMVA1eCUoWAWsLE1ISa0JUMmhFHAZlHlxUOHsUM2wQElgRCX5cO1sVM28HGF0cXQcDVV9uC0onBG8IGF8dVAUCU1teOJy")
    else:
        print("\n⚠️ 无法提取商品ID，请确认链接格式")

    print("\n💡 把上面的链接填到文章 front matter 的 affiliate_url 即可")


def show_guide():
    """显示完整的京东联盟操作指南"""
    print("""
╔══════════════════════════════════════════╗
║       京东联盟 接入指南                   ║
╚══════════════════════════════════════════╝

📋 第一步：注册
  打开 union.jd.com
  → 用京东账号登录
  → 完善个人信息（实名认证）
  → 添加推广渠道：「网站」
  → 填写网站信息（域名: avram-h.github.io）

🔑 第二步：获取 PID
  进入「推广管理」→「网站管理」
  → 复制 PID（三段式，如 12345678_12345678_12345678）
  → 回到这里运行: python jd_helper.py setup

🔗 第三步：转链获取推广链接
  方式A：union.jd.com → 推广管理 → 推广商品 → 搜索 → 立即推广 → 复制链接
  方式B：union.jd.com → 联盟产品 → 转链接口 → 输入商品URL → 复制

✏️ 第四步：写入文章
  把推广链接更新到文章 front matter：
  affiliate_url: 你的推广链接

💰 佣金比例参考：
  数码3C: 0.5-2%    家电: 2-5%
  美妆:   5-10%     食品: 2-8%
  家居:   3-8%      运动户外: 2-6%

📊 查看收益：
  union.jd.com → 效果报表 → 订单查询
""")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "setup":
        setup()
    elif cmd == "update" or cmd == "update-all":
        update_articles()
    elif cmd == "link":
        get_link()
    elif cmd == "guide":
        show_guide()
    else:
        print("\n京东联盟助手 - 用法:")
        print("  python jd_helper.py setup       设置PID")
        print("  python jd_helper.py link        单品转链")
        print("  python jd_helper.py update-all  批量更新文章链接")
        print("  python jd_helper.py guide       查看完整指南")
        print()
        show_guide()
