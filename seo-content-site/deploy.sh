#!/bin/bash
# ============================================
# SEO 站一键构建 + 部署脚本
# 用法: bash deploy.sh [github|vercel|server]
# ============================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}"
echo "╔══════════════════════════════════╗"
echo "║   SEO 内容站 一键部署工具       ║"
echo "╚══════════════════════════════════╝"
echo -e "${NC}"

# ── Step 1: 生成站点 ──
echo -e "${YELLOW}[1/4]${NC} 生成静态站点..."
python3 generate.py

# ── Step 2: 质量检查 ──
echo -e "\n${YELLOW}[2/4]${NC} SEO 质量检查..."

ERRORS=0
# 检查 sitemap
if [ ! -f output/sitemap.xml ]; then
    echo -e "${RED}  ✗${NC} 缺少 sitemap.xml"; ERRORS=$((ERRORS+1))
else
    echo -e "${GREEN}  ✓${NC} sitemap.xml"
fi

# 检查 robots.txt
if [ ! -f output/robots.txt ]; then
    echo -e "${RED}  ✗${NC} 缺少 robots.txt"; ERRORS=$((ERRORS+1))
else
    echo -e "${GREEN}  ✓${NC} robots.txt"
fi

# 检查结构化数据
SCHEMA_COUNT=$(grep -r 'application/ld+json' output/ | wc -l | tr -d ' ')
echo -e "${GREEN}  ✓${NC} 结构化数据: ${SCHEMA_COUNT} 处"

# 检查 meta description
NO_DESC=$(grep -rL 'meta name="description"' output/*.html 2>/dev/null | wc -l | tr -d ' ')
if [ "$NO_DESC" -gt 0 ]; then
    echo -e "${YELLOW}  ⚠${NC} $NO_DESC 个页面缺少 meta description"
fi

# 检查 canonical
NO_CANONICAL=$(grep -rL 'canonical' output/*.html 2>/dev/null | wc -l | tr -d ' ')
if [ "$NO_CANONICAL" -gt 0 ]; then
    echo -e "${YELLOW}  ⚠${NC} $NO_CANONICAL 个页面缺少 canonical"
fi

# 检查图片 alt
IMG_TAGS=$(grep -ro '<img' output/ | wc -l | tr -d ' ')
echo -e "  ℹ  图片标签: ${IMG_TAGS} 个"

# ── Step 3: 部署 ──
DEPLOY_TARGET="${1:-github}"
echo -e "\n${YELLOW}[3/4]${NC} 部署到: ${DEPLOY_TARGET}..."

case "$DEPLOY_TARGET" in
    github)
        echo "  推送到 GitHub Pages..."
        # 检查是否在 git 仓库中
        if git rev-parse --git-dir > /dev/null 2>&1; then
            git add output/ -f
            git commit -m "🚀 Deploy: $(date '+%Y-%m-%d %H:%M')" --allow-empty
            git subtree push --prefix output origin gh-pages
            echo -e "${GREEN}  ✓${NC} 已推送到 gh-pages 分支"
        else
            echo -e "${RED}  ✗${NC} 不在 git 仓库中，请先 git init"
        fi
        ;;
    vercel)
        echo "  部署到 Vercel..."
        if command -v vercel &> /dev/null; then
            cd output && vercel --prod
            echo -e "${GREEN}  ✓${NC} Vercel 部署完成"
        else
            echo -e "${YELLOW}  ⚠${NC} 未安装 Vercel CLI，手动部署: cd output && vercel"
        fi
        ;;
    server)
        echo "  打包上传文件..."
        tar -czf site.tar.gz output/
        echo -e "${GREEN}  ✓${NC} 打包完成: site.tar.gz"
        echo "  请手动上传到服务器并解压到 web 目录"
        ;;
    local)
        echo "  启动本地预览..."
        echo -e "${GREEN}  ✓${NC} 访问 http://localhost:8080"
        cd output && python3 -m http.server 8080
        ;;
    *)
        echo "  未知部署目标: $DEPLOY_TARGET"
        echo "  可选: github | vercel | server | local"
        ;;
esac

# ── Step 4: 搜索引擎 Ping ──
echo -e "\n${YELLOW}[4/4]${NC} 通知搜索引擎..."

CONFIG_FILE="config.json"
DOMAIN=$(python3 -c "import json;print(json.load(open('$CONFIG_FILE'))['site']['domain'])")
SITEMAP_URL="${DOMAIN}/sitemap.xml"

# Google
echo -n "  Google... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    "https://www.google.com/ping?sitemap=${SITEMAP_URL}" 2>/dev/null || echo "fail")
echo "$HTTP_CODE"

# Bing (使用 IndexNow)
echo -n "  Bing (IndexNow)... "
INDEXNOW_KEY=$(python3 -c "import hashlib;print(hashlib.md5(b'${DOMAIN}').hexdigest()[:16])" 2>/dev/null || echo "auto")
curl -s -o /dev/null -w "%{http_code}" \
    -X POST "https://api.indexnow.org/indexnow" \
    -H "Content-Type: application/json" \
    -d "{\"host\":\"$(echo $DOMAIN | sed 's|https\?://||')\",\"key\":\"${INDEXNOW_KEY}\",\"urlList\":[\"${DOMAIN}/\"]}" \
    2>/dev/null || echo "fail"
echo ""

# 百度
echo -n "  百度... "
curl -s -o /dev/null -w "%{http_code}" \
    "https://ziyuan.baidu.com/linksubmit/url?sitemap=${SITEMAP_URL}" 2>/dev/null || echo "fail"
echo ""

echo -e "\n${GREEN}✨ 全部完成！${NC}"
echo -e "站点地址: ${DOMAIN}"
echo -e "站点地图: ${SITEMAP_URL}"
