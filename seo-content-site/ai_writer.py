#!/usr/bin/env python3
"""
AI 辅助文章生成器
- 基于关键词+模板批量生成 Markdown 草稿
- 支持 OpenAI API / 本地模板两种模式
- 自动注入 SEO Front Matter

用法:
  python ai_writer.py --topic "蓝牙音箱推荐" --count 1          # 单篇生成
  python ai_writer.py --batch keywords.txt                      # 批量生成
  python ai_writer.py --keyword "扫地机器人" --outline-only      # 只生成大纲
  python ai_writer.py --keyword "蓝牙音箱" --use-api             # 调用 OpenAI API
"""

import json, os, re, sys, time, argparse
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request

BASE_DIR    = Path(__file__).parent
CONTENT_DIR = BASE_DIR / "content"
CONFIG_FILE = BASE_DIR / "config.json"

TEMPLATES = {
    "推荐榜单": {
        "structure": """---
title: {title}
date: {date}
author: {author}
tags: [{tags}]
category: {category}
keywords: {keywords}
affiliate_url: {affiliate_url}
affiliate_text: 👉 去京东查看最新价格
excerpt: {excerpt}
---

# {title}

{intro}

## 选购{category_name}的关键指标

- **{factor1}**：{factor1_desc}
- **{factor2}**：{factor2_desc}
- **{factor3}**：{factor3_desc}
- **{factor4}**：{factor4_desc}
- **{factor5}**：{factor5_desc}

## TOP {count} 推荐

### 1. {product1_name}

{product1_desc}

- {attr1_label}：{attr1_value}
- {attr2_label}：{attr2_value}
- 价格：约 ¥{price1} 元

### 2. {product2_name}

{product2_desc}

- {attr1_label}：{product2_attr1}
- {attr2_label}：{product2_attr2}
- 价格：约 ¥{price2} 元

### 3. {product3_name}

{product3_desc}

- {attr1_label}：{product3_attr1}
- {attr2_label}：{product3_attr2}
- 价格：约 ¥{price3} 元

## 怎么选？

1. **{scenario1}** → {recommend1}，{reason1}
2. **{scenario2}** → {recommend2}，{reason2}
3. **{scenario3}** → {recommend3}，{reason3}

## 常见问题

**Q：{faq1_q}**
**A：{faq1_a}**

**Q：{faq2_q}**
**A：{faq2_a}**

**Q：{faq3_q}**
**A：{faq3_a}**

## 总结

{conclusion}
""",
        "defaults": {
            "intro": "{category_name}已经成为我们生活中不可或缺的一部分。但市场上品牌和型号繁多，该怎么选呢？这篇{title}从多个维度帮你理清思路。",
            "conclusion": "无论选择哪一款，{year}年的{category_name}技术水平已经非常成熟。建议根据自身预算和使用场景来做决定，适合自己的才是最好的。",
        }
    },
    "单品测评": {
        "structure": """---
title: {title}
date: {date}
author: {author}
tags: [{tags}]
category: {category}
keywords: {keywords}
affiliate_url: {affiliate_url}
affiliate_text: 👉 去京东查看最新价格
excerpt: {excerpt}
rating: {rating}
---

# {title}

{intro}

## 外观设计

{design}

## 性能表现

{performance}

## 使用体验

{experience}

## 优缺点分析

### 优点

- {pro1}
- {pro2}
- {pro3}

### 缺点

- {con1}
- {con2}

## 适合人群

{suitable_for}

## 购买建议

{buy_advice}

## 常见问题

**Q：{faq1_q}**
**A：{faq1_a}**

**Q：{faq2_q}**
**A：{faq2_a}**

## 总结

{conclusion}
""",
        "defaults": {
            "intro": "{title}到底值不值得买？我深度使用了{usage_days}天，从外观、性能、体验三个维度给你最真实的评测。",
            "conclusion": "综合来看，{title}是一款{overall_rating}的产品。{buy_recommendation}",
        }
    },
    "对比评测": {
        "structure": """---
title: {title}
date: {date}
author: {author}
tags: [{tags}]
category: {category}
keywords: {keywords}
affiliate_url: {affiliate_url}
affiliate_text: 👉 去京东对比价格
excerpt: {excerpt}
---

# {title}

{intro}

## 对比维度

本次对比基于以下 {dimension_count} 个核心维度：

- **{dim1}**
- **{dim2}**
- **{dim3}**
- **{dim4}**

## 详细对比

| 对比项 | {product_a} | {product_b} | {product_c} |
|--------|{price_col_a}等|
| {dim1} | {a_dim1} | {b_dim1} | {c_dim1} |
| {dim2} | {a_dim2} | {b_dim2} | {c_dim2} |
| {dim3} | {a_dim3} | {b_dim3} | {c_dim3} |
| {dim4} | {a_dim4} | {b_dim4} | {c_dim4} |
| 价格 | ¥{price_a} | ¥{price_b} | ¥{price_c} |

## 逐款分析

### {product_a}

{analysis_a}

### {product_b}

{analysis_b}

### {product_c}

{analysis_c}

## 选购建议

{recommendation}

## 常见问题

**Q：{faq1_q}**
**A：{faq1_a}**

**Q：{faq2_q}**
**A：{faq2_a}**

## 总结

{conclusion}
"""
    }
}


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def slugify(text):
    s = re.sub(r'[^\w\u4e00-\u9fff]+', '-', text.lower())
    return s.strip('-')


class AIWriter:
    def __init__(self, config):
        self.cfg = config
        self.site = config["site"]

    def generate_outline(self, keyword, template_name="推荐榜单"):
        """基于关键词生成文章大纲"""
        cat_map = {
            "耳机": "digital", "音箱": "digital", "手机": "digital", "电脑": "digital",
            "扫地": "home", "吸尘": "home", "家具": "home", "灯": "home",
            "护肤": "beauty", "化妆": "beauty", "洗面": "beauty", "防晒": "beauty",
        }
        category = "digital"
        for kw, cat in cat_map.items():
            if kw in keyword:
                category = cat
                break

        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "title": f"{datetime.now().year}年{keyword}推荐 TOP5",
            "keyword": keyword,
            "category": category,
            "category_name": keyword.replace("推荐", "").replace("排行", ""),
            "date": today,
            "author": self.site["author"],
            "template": template_name,
            "filename": slugify(f"{today}-{keyword}"),
        }

    def write_draft(self, outline, use_api=False):
        """生成文章草稿"""
        if use_api:
            return self._write_with_api(outline)
        else:
            return self._write_with_template(outline)

    def _write_with_template(self, outline):
        """使用模板填充生成"""
        tmpl_data = TEMPLATES.get(outline["template"], TEMPLATES["推荐榜单"])
        structure = tmpl_data["structure"]
        defaults = tmpl_data.get("defaults", {})

        kw = outline["keyword"]
        cat_name = outline["category_name"]
        year = str(datetime.now().year)
        today = outline["date"]

        # 构建模板变量
        vars_dict = {
            "title": outline["title"],
            "date": today,
            "author": outline["author"],
            "tags": f'{kw}, {outline["category"]}, 性价比, 推荐',
            "category": outline["category"],
            "keywords": f'{kw},推荐,排行,评测',
            "affiliate_url": f'https://search.jd.com/Search?keyword={kw}&enc=utf-8',
            "excerpt": f'深入对比评测{year}年最值得购买的{kw}，从多维度帮你找到最适合的选择。',
            "year": year,
            "category_name": cat_name,
            # 通用占位符
            "intro": f'{cat_name}已经成为我们生活中不可或缺的一部分。但市场上品牌和型号繁多，该怎么选呢？这篇{outline["title"]}从多个维度帮你理清思路。',
            "conclusion": f'无论选择哪一款，{year}年的{cat_name}技术水平已经非常成熟。建议根据自身预算和使用场景来做决定，适合自己的才是最好的。',
            "factor1": "性能", "factor1_desc": "核心参数决定使用体验的上限",
            "factor2": "价格", "factor2_desc": "在预算范围内选择性价比最高的",
            "factor3": "品牌", "factor3_desc": "大品牌质量有保障，售后更放心",
            "factor4": "口碑", "factor4_desc": "真实用户评价比广告更有参考价值",
            "factor5": "设计", "factor5_desc": "颜值和做工同样重要",
            "count": "5",
            "product1_name": f"旗舰款{cat_name}", "product1_desc": "性能强悍，功能全面的顶配之选。适合预算充足、追求极致体验的用户。",
            "product2_name": f"性价比款{cat_name}", "product2_desc": "在性能与价格之间取得完美平衡，是大多数人的首选。",
            "product3_name": f"入门款{cat_name}", "product3_desc": "基础功能齐全，价格亲民，适合初次尝试的用户。",
            "attr1_label": "核心参数", "attr1_value": "顶级配置",
            "attr2_label": "续航/寿命", "attr2_value": "行业领先",
            "price1": "2999", "product2_attr1": "中高端", "product2_attr2": "主流水平",
            "price2": "1499", "product3_attr1": "够用", "product3_attr2": "标准",
            "price3": "599",
            "scenario1": "追求品质", "recommend1": f"旗舰款{cat_name}", "reason1": "各方面都是顶级水准",
            "scenario2": "性价比优先", "recommend2": f"性价比款{cat_name}", "reason2": "花更少的钱获得 80% 的体验",
            "scenario3": "预算有限", "recommend3": f"入门款{cat_name}", "reason3": "基础功能够用，价格友好",
            "faq1_q": f"{cat_name}一般能用多久？", "faq1_a": f"正常使用情况下，{cat_name}可以使用2-5年。建议选择大品牌，质量和售后更有保障。",
            "faq2_q": f"贵的一定好吗？", "faq2_a": "不一定。很多中端产品性价比更高。关键是找到满足自己需求的产品，不必盲目追求旗舰。",
            "faq3_q": f"线上买还是线下买？", "faq3_a": "推荐线上购买。价格更透明，选择更多，退换货也更方便。京东自营是可靠的选择。",
        }

        # 简单模板替换
        result = structure
        for key, val in vars_dict.items():
            result = result.replace(f"{{{key}}}", str(val))

        # 清理未替换的占位符
        result = re.sub(r'\{[^}]+\}', '（待补充）', result)

        return result

    def _write_with_api(self, outline):
        """调用 OpenAI API 生成（需要 API key）"""
        api_key = os.environ.get("OPENAI_API_KEY") or self.cfg.get("openai_api_key", "")
        if not api_key:
            print("❌ 未设置 OPENAI_API_KEY，回退到模板模式")
            return self._write_with_template(outline)

        prompt = f"""你是一个专业的好物推荐写手。请以中文写一篇 SEO 友好的购物推荐文章。

主题：{outline['title']}
分类：{outline['category']}
关键词：{outline['keyword']}

要求：
1. 使用 Markdown 格式，包含 h2/h3 标题
2. 包含至少 3 款产品推荐，每款写详细理由
3. 文末添加常见问题 Q&A（至少3个）
4. 语言亲切专业，避免广告腔
5. 全文 800-1500 字
6. 开头用 --- YAML front matter 包裹元数据

直接输出完整文章，不要额外解释。"""

        try:
            data = json.dumps({
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8,
                "max_tokens": 2500,
            }).encode()

            req = Request("https://api.openai.com/v1/chat/completions", data=data, method="POST")
            req.add_header("Authorization", f"Bearer {api_key}")
            req.add_header("Content-Type", "application/json")

            with urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                content = result["choices"][0]["message"]["content"]
                print(f"  🤖 AI 生成完成 ({len(content)} 字符)")
                return content
        except Exception as e:
            print(f"  ❌ API 调用失败: {e}，回退到模板模式")
            return self._write_with_template(outline)

    def save_draft(self, content, filename):
        """保存草稿到 content/ 目录"""
        # 确保有 front matter
        if not content.strip().startswith("---"):
            # AI 生成的如果没有 front matter，自动添加
            title = filename.replace("-", " ")
            today = datetime.now().strftime("%Y-%m-%d")
            fm = f"""---
title: {title}
date: {today}
author: {self.site["author"]}
tags: [推荐]
category: digital
keywords: {title}
affiliate_url: 
affiliate_text: 👉 去京东查看最新价格
---\n\n"""
            content = fm + content

        # 从 front matter 提取 title 生成更好的文件名
        title_match = re.search(r'title:\s*(.+)', content[:500])
        if title_match:
            filename = slugify(f"{datetime.now().strftime('%Y-%m-%d')}-{title_match.group(1)}")

        filepath = CONTENT_DIR / f"{filename}.md"
        CONTENT_DIR.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"  💾 已保存: {filepath}")
        return filepath


def main():
    parser = argparse.ArgumentParser(description="AI 辅助文章生成器")
    parser.add_argument("--keyword", "-k", type=str, help="关键词（如：蓝牙音箱推荐）")
    parser.add_argument("--batch", "-b", type=str, help="批量关键词文件（每行一个关键词）")
    parser.add_argument("--template", "-t", type=str, default="推荐榜单",
                        choices=["推荐榜单", "单品测评", "对比评测"], help="文章模板")
    parser.add_argument("--use-api", action="store_true", help="使用 OpenAI API")
    parser.add_argument("--outline-only", action="store_true", help="只生成大纲，不写正文")
    parser.add_argument("--count", "-n", type=int, default=1, help="生成篇数")

    args = parser.parse_args()

    config = load_config()
    writer = AIWriter(config)

    keywords = []
    if args.batch:
        with open(args.batch, "r", encoding="utf-8") as f:
            keywords = [line.strip() for line in f if line.strip()]
    elif args.keyword:
        keywords = [args.keyword]
    else:
        # 交互式输入
        print("\n📝 请输入关键词（每行一个，空行结束）:")
        while True:
            line = input().strip()
            if not line:
                break
            keywords.append(line)

    if not keywords:
        print("❌ 未输入任何关键词")
        return

    print(f"\n🎯 准备生成 {len(keywords)} 篇文章\n")

    for kw in keywords:
        outline = writer.generate_outline(kw, args.template)
        print(f"📝 关键词: {kw}")
        print(f"   标题: {outline['title']}")
        print(f"   分类: {outline['category']}")

        if args.outline_only:
            print(f"   文件: {outline['filename']}.md\n")
            continue

        content = writer.write_draft(outline, use_api=args.use_api)
        filepath = writer.save_draft(content, outline["filename"])
        print(f"   ✅ 完成: {filepath.name}\n")

    print(f"✨ 全部完成！运行 python generate.py 即可生成站点。")


if __name__ == "__main__":
    main()
