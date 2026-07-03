#!/usr/bin/env python3
"""
SEO 内容站生成器 v2
新增: Schema.org 结构化数据、面包屑导航、Open Graph/Twitter Card、
      图片支持、robots.txt、自动内链、性能优化
"""
import json, os, re, shutil, hashlib, textwrap
from datetime import datetime
from pathlib import Path
from html import escape

BASE_DIR    = Path(__file__).parent
CONTENT_DIR = BASE_DIR / "content"
OUTPUT_DIR  = BASE_DIR / "output"
TEMPLATE_DIR= BASE_DIR / "templates"
IMAGE_DIR   = BASE_DIR / "images"

# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────
def load_config():
    with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
        return json.load(f)

def slugify(text):
    """中文保留，英文转小写，特殊字符替换为 -"""
    s = re.sub(r'[^\w\u4e00-\u9fff]+', '-', text.lower())
    return s.strip('-')

def date_to_iso(d):
    """确保日期为 ISO 格式"""
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%Y-%m-%d")
    except:
        return datetime.now().strftime("%Y-%m-%d")

def md5_id(s):
    return hashlib.md5(s.encode()).hexdigest()[:8]

# ──────────────────────────────────────────────
# Markdown → HTML 渲染器（增强版）
# ──────────────────────────────────────────────
class MarkdownRenderer:
    @staticmethod
    def to_html(body: str) -> str:
        lines = body.split("\n")
        out, in_list, list_type = [], False, None

        for line in lines:
            s = line.strip()
            if not s:
                if in_list:
                    out.append(f"</{list_type}>"); in_list = False
                continue

            # 标题 h2-h4
            for lvl in range(2, 5):
                m = re.match(rf'^{"#"*lvl}\s+(.+)', s)
                if m:
                    if in_list:
                        out.append(f"</{list_type}>"); in_list = False
                    out.append(f'<h{lvl}>{m.group(1)}</h{lvl}>')
                    break
            else:
                # 列表
                ul = re.match(r'^[-*]\s+(.+)', s)
                ol = re.match(r'^\d+\.\s+(.+)', s)
                if ul:
                    if not in_list or list_type != "ul":
                        if in_list: out.append(f"</{list_type}>")
                        out.append("<ul>"); in_list = True; list_type = "ul"
                    out.append(f"<li>{ul.group(1)}</li>")
                elif ol:
                    if not in_list or list_type != "ol":
                        if in_list: out.append(f"</{list_type}>")
                        out.append("<ol>"); in_list = True; list_type = "ol"
                    out.append(f"<li>{ol.group(1)}</li>")
                else:
                    if in_list:
                        out.append(f"</{list_type}>"); in_list = False
                    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
                    s = re.sub(r'`(.+?)`', r'<code>\1</code>', s)
                    s = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2" target="_blank" rel="nofollow noopener">\1</a>', s)
                    # 表格行
                    if '|' in s and s.count('|') >= 2:
                        cells = [c.strip() for c in s.strip('|').split('|')]
                        out.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
                    else:
                        out.append(f"<p>{s}</p>")

        if in_list: out.append(f"</{list_type}>")
        return "\n".join(out)

# ──────────────────────────────────────────────
# Schema.org 结构化数据生成器
# ──────────────────────────────────────────────
class SchemaGenerator:
    @staticmethod
    def organization(site):
        return json.dumps({
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": site["name"],
            "url": site["domain"],
            "logo": f"{site['domain']}/images/logo.png",
            "sameAs": site.get("social_links", []),
        }, ensure_ascii=False)

    @staticmethod
    def website(site):
        return json.dumps({
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": site["name"],
            "url": site["domain"],
            "potentialAction": {
                "@type": "SearchAction",
                "target": f"{site['domain']}/search?q={{search_term_string}}",
                "query-input": "required name=search_term_string"
            }
        }, ensure_ascii=False)

    @staticmethod
    def breadcrumb(site, article):
        items = [
            {"@type": "ListItem", "position": 1, "name": "首页", "item": site["domain"]},
            {"@type": "ListItem", "position": 2, "name": article["category"], "item": f"{site['domain']}/category/{article['category']}"},
            {"@type": "ListItem", "position": 3, "name": article["title"]},
        ]
        return json.dumps({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}, ensure_ascii=False)

    @staticmethod
    def article(site, article, html_body):
        return json.dumps({
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": article["title"],
            "description": article["excerpt"],
            "author": {"@type": "Person", "name": article["author"]},
            "datePublished": article["date"],
            "dateModified": article.get("date_modified", article["date"]),
            "image": article.get("image_url") or f"{site['domain']}/images/default.jpg",
            "url": article["canonical_url"],
            "publisher": {"@type": "Organization", "name": site["name"]},
            "mainEntityOfPage": {"@type": "WebPage", "@id": article["canonical_url"]},
            "keywords": ", ".join(article["tags"]),
        }, ensure_ascii=False)

    @staticmethod
    def faq(qa_list):
        """FAQ 结构化数据"""
        items = [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa_list]
        return json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": items}, ensure_ascii=False)

    @staticmethod
    def product_review(site, article):
        """产品评测结构化数据"""
        return json.dumps({
            "@context": "https://schema.org",
            "@type": "Product",
            "name": article["title"],
            "description": article["excerpt"],
            "review": {
                "@type": "Review",
                "reviewRating": {
                    "@type": "Rating",
                    "ratingValue": article.get("rating", "4.5"),
                    "bestRating": "5"
                },
                "author": {"@type": "Person", "name": article["author"]}
            },
            "offers": {
                "@type": "Offer",
                "url": article.get("affiliate_url", ""),
                "availability": "https://schema.org/InStock",
            }
        }, ensure_ascii=False)


# ──────────────────────────────────────────────
# 站点生成器
# ──────────────────────────────────────────────
class SiteGenerator:
    def __init__(self, config):
        self.cfg = config
        self.site = config["site"]
        self.articles = []
        self.tags = {}
        self.categories = {}

    # ── 文章解析 ──
    def parse_markdown_article(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()

        meta, body = {}, raw
        fm = re.match(r'^---\s*\n(.*?)\n---\s*\n', raw, re.DOTALL)
        if fm:
            body = raw[fm.end():]
            for line in fm.group(1).strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k in ("tags", "related_posts"):
                        meta[k] = [t.strip() for t in v.strip("[]").split(",") if t.strip()]
                    elif k == "faq":
                        meta[k] = v  # 保持原样，后续解析
                    else:
                        meta[k] = v

        title_m = re.match(r'^#\s+(.+)', body.strip())
        title = title_m.group(1).strip() if title_m else meta.get("title", filepath.stem)
        body = re.sub(r'^#\s+.+\n', '', body.strip(), count=1) if title_m else body.strip()

        excerpt = meta.get("excerpt", re.sub(r'[#*`\[\]]', '', body[:250]).strip() + "...")
        slug = meta.get("slug", filepath.stem)

        # 检测 FAQ 区块（## 常见问题 或 ## FAQ 下面的 Q&A）
        faq_blocks = []
        faq_section = re.search(r'(?:##\s*(?:常见问题|FAQ|问答|Q&A).*?)\n((?:\*\*Q[：:].*?\n.*?\*\*A[：:].*?\n?)+)', body, re.DOTALL | re.IGNORECASE)
        if faq_section:
            for qa in re.finditer(r'\*\*Q[：:](.*?)\*\*\s*\n\s*\*\*A[：:](.*?)\*\*', faq_section.group(1)):
                faq_blocks.append((qa.group(1).strip(), qa.group(2).strip()))

        return {
            "title": title,
            "slug": slug,
            "date": date_to_iso(meta.get("date", "")),
            "date_modified": date_to_iso(meta.get("date_modified", meta.get("date", ""))),
            "author": meta.get("author", self.site["author"]),
            "tags": meta.get("tags", []),
            "category": meta.get("category", "uncategorized"),
            "excerpt": excerpt,
            "body": body,
            "keywords": meta.get("keywords", ", ".join(meta.get("tags", []))),
            "affiliate_url": meta.get("affiliate_url", ""),
            "affiliate_text": meta.get("affiliate_text", "👉 去购买"),
            "image": meta.get("image", ""),
            "image_url": f"{self.site['domain']}/images/{meta['image']}" if meta.get("image") else "",
            "canonical_url": f"{self.site['domain']}/{slug}.html",
            "rating": meta.get("rating", ""),
            "faq": faq_blocks,
            "is_review": "评测" in title or "推荐" in title or "对比" in title,
        }

    def collect_articles(self):
        self.articles = []
        for md_file in sorted(CONTENT_DIR.glob("*.md")):
            a = self.parse_markdown_article(md_file)
            self.articles.append(a)
            for tag in a["tags"]:
                self.tags.setdefault(tag, []).append(a)
            self.categories.setdefault(a["category"], []).append(a)
        self.articles.sort(key=lambda a: a["date"], reverse=True)
        print(f"📄 已收集 {len(self.articles)} 篇文章")

    # ── HTML 生成 ──
    def _page_html(self, meta_extra="", body_html="", body_class="") -> str:
        """通用页面骨架"""
        ga_id = self.cfg["seo"].get("google_analytics_id", "")
        bd_id = self.cfg["seo"].get("baidu_tongji_id", "")
        gsc_tag = self.cfg["seo"].get("google_search_console", "")

        analytics = ""
        if ga_id:
            analytics += f"""<script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{ga_id}');</script>"""
        gsc_meta = f'<meta name="google-site-verification" content="{gsc_tag}" />\n        ' if gsc_tag else ""
        if bd_id:
            analytics += f"""<script>var _hmt=_hmt||[];(function(){{var hm=document.createElement("script");hm.src="https://hm.baidu.com/hm.js?{bd_id}";var s=document.getElementsByTagName("script")[0];s.parentNode.insertBefore(hm,s);}})();</script>"""

        # 侧边栏热门
        hot_items = "\n".join(
            f'<li><a href="/{a["slug"]}.html">{a["title"]}</a></li>'
            for a in self.articles[:8]
        )
        # 侧边栏标签
        top_tags = sorted(self.tags.keys(), key=lambda t: len(self.tags[t]), reverse=True)[:18]
        tag_items = "\n".join(
            f'<a href="/tag/{t}.html" class="tag-pill">{t}</a>' for t in top_tags
        )

        # 内链：关键词→文章映射
        internal_links = "\n".join(
            f'<li><a href="/{a["slug"]}.html">{a["title"]}</a></li>'
            for a in self.articles[:5]
        )

        return f"""<!DOCTYPE html>
<html lang="{self.site['language']}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
{meta_extra}
{gsc_meta}<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="dns-prefetch" href="https://pagead2.googlesyndication.com">
<link rel="alternate" type="application/rss+xml" title="RSS" href="/feed.xml">
{analytics}
<style>
:root{{--primary:#e74c3c;--primary-dark:#c0392b;--bg:#fff;--bg2:#f9fafb;--text:#1a1a2e;--text2:#6b7280;--border:#e5e7eb;--radius:12px;--shadow:0 1px 3px rgba(0,0,0,.08);--shadow-hover:0 8px 25px rgba(0,0,0,.12)}}
*,::before,::after{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;color:var(--text);background:var(--bg2);line-height:1.75;-webkit-font-smoothing:antialiased}}
a{{color:var(--primary);text-decoration:none}}a:hover{{text-decoration:underline}}
.container{{max-width:1200px;margin:0 auto;padding:0 20px}}
/* Header */
.site-header{{background:var(--bg);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100;box-shadow:var(--shadow);backdrop-filter:blur(8px)}}
.site-header .container{{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;flex-wrap:wrap;gap:8px}}
.logo{{font-size:1.4rem;font-weight:800;color:var(--primary);letter-spacing:-.5px}}
.logo:hover{{text-decoration:none}}
.nav-links{{display:flex;gap:20px;font-size:.92rem}}
.nav-links a{{color:var(--text);font-weight:500;transition:color .2s}}
.nav-links a:hover{{color:var(--primary);text-decoration:none}}
/* Layout */
.main-layout{{display:flex;gap:28px;margin-top:28px;align-items:flex-start}}
.content-area{{flex:1;min-width:0}}
.sidebar{{width:300px;flex-shrink:0;position:sticky;top:80px}}
/* Cards */
.card{{background:var(--bg);border-radius:var(--radius);box-shadow:var(--shadow);padding:22px;margin-bottom:20px;transition:all .25s;border:1px solid var(--border)}}
.card:hover{{box-shadow:var(--shadow-hover);transform:translateY(-2px)}}
.card h2{{font-size:1.2rem;margin-bottom:6px;line-height:1.4}}
.card h2 a{{color:var(--text)}}.card h2 a:hover{{color:var(--primary);text-decoration:none}}
.card .meta{{font-size:.8rem;color:var(--text2);margin-bottom:8px}}
.card .excerpt{{font-size:.92rem;color:var(--text2);line-height:1.6}}
.card-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:18px}}
/* Article */
.article-full{{background:var(--bg);border-radius:var(--radius);box-shadow:var(--shadow);padding:36px;border:1px solid var(--border)}}
.article-full h1{{font-size:2rem;margin-bottom:8px;line-height:1.3}}
.article-full .article-meta{{font-size:.85rem;color:var(--text2);margin-bottom:6px;padding-bottom:16px;border-bottom:1px solid var(--border);display:flex;flex-wrap:wrap;gap:4px 12px}}
.article-full h2{{font-size:1.45rem;margin:30px 0 12px;color:var(--primary);padding-bottom:6px;border-bottom:2px solid var(--bg2)}}
.article-full h3{{font-size:1.2rem;margin:22px 0 8px}}
.article-full p{{margin-bottom:14px;font-size:1.02rem}}
.article-full ul,.article-full ol{{margin:10px 0 16px 28px}}
.article-full li{{margin-bottom:6px}}
.article-full table{{width:100%;border-collapse:collapse;margin:16px 0;font-size:.92rem}}
.article-full th,.article-full td{{border:1px solid var(--border);padding:10px 14px;text-align:left}}
.article-full th{{background:var(--bg2);font-weight:600}}
.article-full blockquote{{border-left:4px solid var(--primary);padding:10px 18px;margin:16px 0;background:var(--bg2);border-radius:0 var(--radius) var(--radius) 0;color:var(--text2)}}
.article-full code{{background:var(--bg2);padding:2px 6px;border-radius:4px;font-size:.88em}}
/* Breadcrumb */
.breadcrumb{{font-size:.85rem;color:var(--text2);margin-bottom:16px;padding:10px 0}}
.breadcrumb a{{color:var(--text2)}}
.breadcrumb span{{margin:0 6px}}
/* Tags */
.tag-pill{{display:inline-block;background:var(--bg2);color:var(--text);padding:4px 12px;border-radius:20px;font-size:.8rem;border:1px solid var(--border);transition:all .2s;margin:3px}}
.tag-pill:hover{{background:var(--primary);color:#fff;border-color:var(--primary);text-decoration:none}}
/* Affiliate & CTA */
.affiliate-btn{{display:inline-block;background:linear-gradient(135deg,#f97316,#ef4444);color:#fff!important;padding:14px 32px;border-radius:30px;font-weight:700;font-size:1.05rem;box-shadow:0 6px 20px rgba(239,68,68,.35);transition:all .25s;text-align:center;margin:20px 0}}
.affiliate-btn:hover{{transform:translateY(-3px);box-shadow:0 10px 28px rgba(239,68,68,.45);text-decoration:none}}
.cta-box{{background:linear-gradient(135deg,#fff5f5,#fff);border:2px solid var(--primary);border-radius:var(--radius);padding:24px;margin:24px 0;text-align:center}}
.cta-box h3{{color:var(--primary);margin-bottom:8px}}
/* Sidebar widgets */
.sidebar .widget-title{{font-size:1rem;font-weight:700;margin-bottom:10px;color:var(--text)}}
.sidebar ul{{list-style:none;padding:0}}
.sidebar li{{margin-bottom:10px;font-size:.88rem;border-bottom:1px dashed var(--border);padding-bottom:8px}}
.sidebar li:last-child{{border-bottom:none}}
.ad-placeholder{{background:var(--bg);border:2px dashed var(--border);border-radius:var(--radius);padding:30px;text-align:center;color:var(--text2);font-size:.85rem;margin-bottom:20px;min-height:280px;display:flex;align-items:center;justify-content:center}}
/* FAQ */
.faq-item{{margin-bottom:14px}}
.faq-item .question{{font-weight:700;color:var(--primary);cursor:pointer;font-size:1.02rem}}
.faq-item .answer{{margin-top:4px;color:var(--text2);font-size:.95rem}}
/* Pagination */
.pagination{{display:flex;justify-content:center;gap:6px;margin:36px 0}}
.pagination a,.pagination span{{padding:9px 16px;border-radius:8px;border:1px solid var(--border);font-size:.9rem;font-weight:500;transition:all .2s}}
.pagination a:hover{{background:var(--primary);color:#fff;border-color:var(--primary);text-decoration:none}}
.pagination .current{{background:var(--primary);color:#fff;border-color:var(--primary)}}
/* Footer */
.site-footer{{background:var(--bg);border-top:1px solid var(--border);margin-top:60px;padding:36px 20px;text-align:center;color:var(--text2);font-size:.85rem}}
.site-footer a{{color:var(--text2);margin:0 8px}}
/* Responsive */
@media(max-width:768px){{.main-layout{{flex-direction:column}}.sidebar{{width:100%;position:static}}.card-grid{{grid-template-columns:1fr}}.article-full{{padding:22px}}.nav-links{{overflow-x:auto;gap:14px;white-space:nowrap;padding-bottom:4px}}}}
</style>
</head>
<body>
<header class="site-header"><div class="container">
<a href="/" class="logo">{self.site['name']}</a>
<nav class="nav-links">
<a href="/">首页</a>
<a href="/category/digital">数码</a>
<a href="/category/home">家居</a>
<a href="/category/beauty">美妆</a>
<a href="/category/lifestyle">生活</a>
</nav>
</div></header>

<div class="container">
<div class="main-layout">
<main class="content-area {body_class}">
{body_html}
</main>
<aside class="sidebar">
{{ad_sidebar_top}}
<div class="card">
<p class="widget-title">🔥 热门推荐</p>
<ul>{hot_items}</ul>
</div>
<div class="card">
<p class="widget-title">📂 最新文章</p>
<ul>{internal_links}</ul>
</div>
<div class="card">
<p class="widget-title">🏷️ 标签</p>
<div style="display:flex;flex-wrap:wrap;gap:4px">{tag_items}</div>
</div>
{{ad_sidebar_bottom}}
</aside>
</div></div>

<footer class="site-footer">
<p>&copy; {datetime.now().year} {self.site['name']}</p>
<p style="margin-top:6px">
<a href="/about.html">关于</a>·
<a href="/privacy.html">隐私政策</a>·
<a href="/sitemap.xml">网站地图</a>·
<a href="/feed.xml">RSS</a>
</p>
<p style="margin-top:6px;font-size:.78rem">本站含有联盟链接，购物请理性选择</p>
</footer>
</body>
</html>"""

    # ── 文章页 ──
    def generate_article_page(self, article):
        body_html = MarkdownRenderer.to_html(article["body"])

        # 内链自动插入：在正文中查找其他文章标题关键词，自动加链接
        for other in self.articles:
            if other["slug"] == article["slug"]: continue
            kw = other["title"][:8]
            if kw in body_html and kw not in article["title"]:
                body_html = body_html.replace(kw, f'<a href="/{other["slug"]}.html">{kw}</a>', 1)

        # 文中广告位
        paras = body_html.split("\n")
        ad_positions = [max(2, len(paras)//3), max(4, len(paras)*2//3)]
        for pos in sorted(ad_positions, reverse=True):
            if pos < len(paras):
                paras.insert(pos, '<div class="ad-slot in-content-ad"><!-- 文中广告 --></div>')
        body_html = "\n".join(paras)

        # 联盟按钮
        cta = ""
        if article["affiliate_url"]:
            cta = f'<div class="cta-box"><h3>🔥 心动了？</h3><p>点击下方按钮查看最新价格</p><a href="{article["affiliate_url"]}" target="_blank" rel="nofollow sponsored" class="affiliate-btn">{article["affiliate_text"]}</a></div>'

        # FAQ 区块
        faq_html = ""
        if article["faq"]:
            faq_html = '<div class="card" style="margin-top:24px"><h2>❓ 常见问题</h2>'
            for q, a in article["faq"]:
                faq_html += f'<div class="faq-item"><p class="question">Q: {q}</p><p class="answer">A: {a}</p></div>'
            faq_html += '</div>'

        # 相关推荐
        related = [a for a in self.articles if a["slug"] != article["slug"] and (set(a["tags"]) & set(article["tags"]))][:6]
        related_html = ""
        if related:
            related_html = '<div class="card" style="margin-top:24px"><p class="widget-title">📖 相关推荐</p><ul>'
            for r in related:
                related_html += f'<li><a href="/{r["slug"]}.html">{r["title"]}</a></li>'
            related_html += '</ul></div>'

        # 面包屑
        breadcrumb = f"""<nav class="breadcrumb" aria-label="Breadcrumb">
<a href="/">首页</a><span>›</span>
<a href="/category/{article['category']}">{article['category']}</a><span>›</span>
<span>{article['title']}</span></nav>"""

        # 文章元信息
        tags_html = " ".join(f'<a href="/tag/{t}.html" class="tag-pill">{t}</a>' for t in article["tags"])

        content = f"""{breadcrumb}
<article class="article-full">
<h1>{article['title']}</h1>
<div class="article-meta">
<span>📅 {article['date']}</span>
<span>✍️ {article['author']}</span>
<span>📂 <a href="/category/{article['category']}">{article['category']}</a></span>
</div>
<div style="margin:12px 0">{tags_html}</div>
{body_html}
{cta}
</article>
{faq_html}
{related_html}"""

        # 选择结构化数据类型
        if article["is_review"]:
            schema = SchemaGenerator.product_review(self.site, article)
        else:
            schema = SchemaGenerator.article(self.site, article, body_html[:500])
        schema += "\n" + SchemaGenerator.breadcrumb(self.site, article)

        if article["faq"]:
            schema += "\n" + SchemaGenerator.faq(article["faq"])

        meta = "\n".join([
            f"<title>{article['title']} - {self.site['name']}</title>",
            f'<meta name="description" content="{escape(article["excerpt"])}">',
            f'<meta name="keywords" content="{article["keywords"]}">',
            f'<link rel="canonical" href="{article["canonical_url"]}">',
            f'<meta property="og:title" content="{escape(article["title"])}">',
            f'<meta property="og:description" content="{escape(article["excerpt"])}">',
            f'<meta property="og:type" content="article">',
            f'<meta property="og:url" content="{article["canonical_url"]}">',
            f'<meta property="og:site_name" content="{self.site["name"]}">',
            f'<meta property="article:published_time" content="{article["date"]}">',
            f'<meta property="article:author" content="{article["author"]}">',
            f'<meta property="article:tag" content="{", ".join(article["tags"])}">',
            f'<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:title" content="{escape(article["title"])}">',
            f'<meta name="twitter:description" content="{escape(article["excerpt"])}">',
        ])
        if article["image_url"]:
            meta += f'\n<meta property="og:image" content="{article["image_url"]}">'
            meta += f'\n<meta name="twitter:image" content="{article["image_url"]}">'

        meta += f'\n<script type="application/ld+json">{schema}</script>'

        html = self._page_html(meta_extra=meta, body_html=content)
        self._write(OUTPUT_DIR / f"{article['slug']}.html", html)
        print(f"  ✅ {article['slug']}.html")

    # ── 首页 ──
    def generate_index_page(self, page_num=1):
        per_page = self.cfg["content"]["articles_per_page"]
        total_pages = max(1, (len(self.articles) + per_page - 1) // per_page)
        start = (page_num - 1) * per_page
        page_articles = self.articles[start:start + per_page]

        cards = ""
        for i, a in enumerate(page_articles):
            cards += f"""<article class="card">
<h2><a href="/{a['slug']}.html">{a['title']}</a></h2>
<div class="meta">📅 {a['date']} · 📂 {a['category']}</div>
<p class="excerpt">{a['excerpt']}</p>
</article>"""
            if i == 3:
                cards += '<div class="ad-slot in-list-ad"><!-- 列表广告 --></div>'

        # 分页
        pg = ""
        if total_pages > 1:
            pg = '<nav class="pagination" aria-label="Page navigation">'
            if page_num > 1:
                prev = "/" if page_num == 2 else f"/page/{page_num-1}.html"
                pg += f'<a href="{prev}" rel="prev">← 上一页</a>'
            for p in range(1, total_pages + 1):
                if p == page_num:
                    pg += f'<span class="current" aria-current="page">{p}</span>'
                else:
                    url = "/" if p == 1 else f"/page/{p}.html"
                    pg += f'<a href="{url}">{p}</a>'
            if page_num < total_pages:
                pg += f'<a href="/page/{page_num+1}.html" rel="next">下一页 →</a>'
            pg += '</nav>'

        title = self.site["tagline"] if page_num == 1 else f"第{page_num}页 - {self.site['name']}"
        desc = self.site["tagline"]
        canonical = self.site["domain"] if page_num == 1 else f"{self.site['domain']}/page/{page_num}.html"

        meta = "\n".join([
            f"<title>{title}</title>",
            f'<meta name="description" content="{escape(desc)}">',
            f'<link rel="canonical" href="{canonical}">',
            f'<meta property="og:title" content="{escape(title)}">',
            f'<meta property="og:description" content="{escape(desc)}">',
            f'<meta property="og:type" content="website">',
            f'<meta property="og:url" content="{canonical}">',
        ])
        schema = SchemaGenerator.website(self.site) + "\n" + SchemaGenerator.organization(self.site)
        meta += f'\n<script type="application/ld+json">{schema}</script>'

        body = f'<h1 style="font-size:1.6rem;margin-bottom:20px;font-weight:800">{self.site["tagline"]}</h1>\n<div class="card-grid">{cards}</div>\n{pg}'
        html = self._page_html(meta_extra=meta, body_html=body)
        path = OUTPUT_DIR / ("index.html" if page_num == 1 else f"page/{page_num}/index.html")
        self._write(path, html)
        if page_num == 1: print(f"  🏠 index.html")

    # ── 分类页 ──
    def generate_category_pages(self):
        for cat, arts in self.categories.items():
            cards = "".join(
                f'<article class="card"><h2><a href="/{a["slug"]}.html">{a["title"]}</a></h2><div class="meta">📅 {a["date"]}</div><p class="excerpt">{a["excerpt"]}</p></article>'
                for a in arts
            )
            title = f"📂 {cat} - {self.site['name']}"
            meta = f"<title>{title}</title><meta name=\"description\" content=\"{cat}分类下的所有文章\"><link rel=\"canonical\" href=\"{self.site['domain']}/category/{cat}\">"
            body = f"<h1 style=\"font-size:1.5rem;margin-bottom:16px\">📂 {cat} <span style=\"color:var(--text2);font-size:.9rem\">({len(arts)}篇)</span></h1><div class=\"card-grid\">{cards}</div>"
            self._write(OUTPUT_DIR / f"category/{cat}/index.html", self._page_html(meta, body))
            print(f"  📂 category/{cat}/")

    # ── 标签页 ──
    def generate_tag_pages(self):
        for tag, arts in self.tags.items():
            cards = "".join(
                f'<article class="card"><h2><a href="/{a["slug"]}.html">{a["title"]}</a></h2><div class="meta">📅 {a["date"]}</div></article>'
                for a in arts
            )
            title = f"🏷️ {tag} - {self.site['name']}"
            meta = f"<title>{title}</title><link rel=\"canonical\" href=\"{self.site['domain']}/tag/{tag}.html\">"
            body = f"<h1>🏷️ {tag} <span style=\"color:var(--text2);font-size:.9rem\">({len(arts)}篇)</span></h1><div class=\"card-grid\">{cards}</div>"
            self._write(OUTPUT_DIR / f"tag/{tag}.html", self._page_html(meta, body))
        print(f"  🏷️  {len(self.tags)} 个标签页")

    # ── SEO 文件 ──
    def generate_sitemap(self):
        urls = [(self.site["domain"], "1.0", "daily")]
        for a in self.articles:
            urls.append((a["canonical_url"], "0.8", "weekly"))
        for cat in self.categories:
            urls.append((f"{self.site['domain']}/category/{cat}", "0.6", "weekly"))
        for tag in self.tags:
            urls.append((f"{self.site['domain']}/tag/{tag}.html", "0.4", "monthly"))

        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for url, pri, freq in urls:
            xml += f"  <url><loc>{url}</loc><changefreq>{freq}</changefreq><priority>{pri}</priority></url>\n"
        xml += '</urlset>'
        self._write(OUTPUT_DIR / "sitemap.xml", xml)
        print(f"  🗺️  sitemap.xml")

    def generate_robots_txt(self):
        content = f"""User-agent: *
Allow: /
Disallow: /admin/
Sitemap: {self.site['domain']}/sitemap.xml

User-agent: Googlebot
Allow: /
Sitemap: {self.site['domain']}/sitemap.xml

User-agent: Baiduspider
Allow: /
Sitemap: {self.site['domain']}/sitemap.xml
"""
        self._write(OUTPUT_DIR / "robots.txt", content)
        print(f"  🤖 robots.txt")

    def generate_rss(self):
        items = ""
        for a in self.articles[:30]:
            items += f"""<item>
<title>{escape(a['title'])}</title>
<link>{a['canonical_url']}</link>
<description>{escape(a['excerpt'])}</description>
<pubDate>{a['date']}T08:00:00+08:00</pubDate>
<guid isPermaLink="true">{a['canonical_url']}</guid>
</item>"""

        rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<title>{self.site['name']}</title>
<link>{self.site['domain']}</link>
<description>{self.site['tagline']}</description>
<language>{self.site['language']}</language>
<lastBuildDate>{datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')}</lastBuildDate>
<atom:link href="{self.site['domain']}/feed.xml" rel="self" type="application/rss+xml"/>
{items}
</channel>
</rss>"""
        self._write(OUTPUT_DIR / "feed.xml", rss)
        print(f"  📡 feed.xml")

    def generate_static_pages(self):
        """关于页、隐私政策页"""
        about = self._page_html(
            f"<title>关于我们 - {self.site['name']}</title>",
            f'<div class="article-full"><h1>📖 关于{self.site["name"]}</h1><p>我们致力于发现和推荐优质好物，帮助您做出更明智的消费决策。所有推荐均基于真实体验和客观评测。</p></div>'
        )
        privacy = self._page_html(
            f"<title>隐私政策 - {self.site['name']}</title>",
            '<div class="article-full"><h1>🔒 隐私政策</h1><p>本站使用 Google Analytics 统计访问数据。我们不会收集或出售您的个人信息。本站含有联盟营销链接，点击购买我们可能获得佣金。</p></div>'
        )
        self._write(OUTPUT_DIR / "about.html", about)
        self._write(OUTPUT_DIR / "privacy.html", privacy)
        print(f"  📄 about.html, privacy.html")

        # Google Search Console 验证文件
        gsc = self.cfg["seo"].get("google_search_console", "")
        if gsc and gsc.endswith(".html"):
            self._write(OUTPUT_DIR / gsc, f"google-site-verification: {gsc}")
            print(f"  🔍 GSC 验证文件: {gsc}")

    # ── 写入辅助 ──
    def _write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    # ── 广告注入 ──
    # ── 广告注入 ──
    def _inject_ads(self):
        """从 config 读取广告代码，注入到所有 HTML 页面"""
        import glob
        ad_cfg = self.cfg.get("ads", {})
        sidebar_top = ad_cfg.get("sidebar_top", "")
        sidebar_bottom = ad_cfg.get("sidebar_bottom", "")
        in_content = ad_cfg.get("in_content", "")
        in_list = ad_cfg.get("in_list", "")
        auto_ads = ad_cfg.get("auto_ads", "")

        injected = False
        for html_file in glob.glob(str(OUTPUT_DIR / "**/*.html"), recursive=True):
            with open(html_file, "r", encoding="utf-8") as f:
                html = f.read()

            dirty = False

            if auto_ads:
                html = html.replace("</head>", auto_ads + "\n</head>")
                dirty = injected = True

            if sidebar_top:
                html = html.replace("{ad_sidebar_top}", sidebar_top)
                dirty = injected = True
            else:
                html = html.replace("{ad_sidebar_top}", "")

            if sidebar_bottom:
                html = html.replace("{ad_sidebar_bottom}", sidebar_bottom)
                dirty = injected = True
            else:
                html = html.replace("{ad_sidebar_bottom}", "")

            if in_content:
                html = html.replace(
                    '<div class="ad-slot in-content-ad"><!-- 文中广告 --></div>',
                    '<div class="ad-slot in-content-ad">' + in_content + '</div>'
                )
                dirty = injected = True
            else:
                html = html.replace(
                    '<div class="ad-slot in-content-ad"><!-- 文中广告 --></div>', ""
                )

            if in_list:
                html = html.replace(
                    '<div class="ad-slot in-list-ad"><!-- 列表广告 --></div>',
                    '<div class="ad-slot in-list-ad">' + in_list + '</div>'
                )
                dirty = injected = True
            else:
                html = html.replace(
                    '<div class="ad-slot in-list-ad"><!-- 列表广告 --></div>', ""
                )

            if dirty:
                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(html)

        if injected:
            print("\n💰 广告代码已注入")
        else:
            print("\n💡 广告未配置，在 config.json → ads 中填入 AdSense 代码即可变现")
    def run(self):
        print("\n🚀 开始生成站点 v2...\n")
        if OUTPUT_DIR.exists():
            shutil.rmtree(OUTPUT_DIR)
        OUTPUT_DIR.mkdir()

        self.collect_articles()
        if not self.articles:
            print("⚠️  未找到文章! 请在 content/ 下添加 .md 文件")
            return

        print(f"\n📝 生成 {len(self.articles)} 篇文章...")
        for a in self.articles:
            self.generate_article_page(a)

        print(f"\n🏠 生成首页 + 分类 + 标签...")
        per_page = self.cfg["content"]["articles_per_page"]
        total_pages = max(1, (len(self.articles) + per_page - 1) // per_page)
        for p in range(1, total_pages + 1):
            self.generate_index_page(p)
        self.generate_category_pages()
        self.generate_tag_pages()

        print(f"\n🗺️ 生成 SEO 文件...")
        self.generate_sitemap()
        self.generate_robots_txt()
        self.generate_rss()
        self.generate_static_pages()

        # ── 注入广告代码 ──
        self._inject_ads()

        print(f"\n{'='*50}")
        print(f"✨ 完成！→ {OUTPUT_DIR}/")
        print(f"   文章: {len(self.articles)} | 标签: {len(self.tags)} | 分类: {len(self.categories)}")
        print(f"   总页面: {len(self.articles) + total_pages + len(self.categories) + len(self.tags) + 4}")
        print(f"{'='*50}\n")


if __name__ == "__main__":
    gen = SiteGenerator(load_config())
    gen.run()
