# 💰 广告接入实战指南

## 快速概览

站点已预留 5 个广告位，只需在 `config.json` 填入代码即可：

| 广告位 | config.json 字段 | 位置 | 尺寸建议 |
|--------|-----------------|------|---------|
| 侧边栏上 | `ads.sidebar_top` | 文章右侧栏顶部 | 300×250 |
| 侧边栏下 | `ads.sidebar_bottom` | 文章右侧栏底部 | 300×600 |
| 文中广告 | `ads.in_content` | 文章段落之间（2处） | 728×90 或自适应 |
| 列表广告 | `ads.in_list` | 首页文章列表中间 | 自适应 |
| 自动广告 | `ads.auto_ads` | 全站自动插入 | Google Auto Ads 脚本 |

---

## 方案一：Google AdSense（推荐首选）

### 申请条件
- 域名已上线（不能用 localhost）
- 网站有足够原创内容（建议 20+ 篇文章）
- 符合 AdSense 政策（有关于页、隐私页 → 已自动生成）

### 步骤

**1. 注册 AdSense**
访问 [adsense.google.com](https://adsense.google.com)，用 Google 账号注册。

**2. 获取广告代码**

审批通过后，在 AdSense 后台：
- 广告 → 按广告单元 → 创建展示广告单元
- 分别创建 300×250、300×600、自适应 三个广告单元
- 复制每个广告单元的代码

**3. 获取 Auto Ads 代码**
- 广告 → 概览 → 获取代码
- 复制那段 `<script>` 代码

**4. 填入 config.json**

```json
{
  "ads": {
    "enabled": true,
    "sidebar_top": "<script async src=\"https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-你的ID\" crossorigin=\"anonymous\"></script><ins class=\"adsbygoogle\" style=\"display:block\" data-ad-client=\"ca-pub-你的ID\" data-ad-slot=\"1234567890\" data-ad-format=\"auto\"></ins><script>(adsbygoogle = window.adsbygoogle || []).push({});</script>",
    "sidebar_bottom": "<ins class=\"adsbygoogle\" style=\"display:block\" data-ad-client=\"ca-pub-你的ID\" data-ad-slot=\"9876543210\" data-ad-format=\"vertical\"></ins><script>(adsbygoogle = window.adsbygoogle || []).push({});</script>",
    "auto_ads": "<script async src=\"https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-你的ID\" crossorigin=\"anonymous\"></script>"
  }
}
```

> ⚠️ 把 `ca-pub-你的ID` 和 `data-ad-slot` 替换为你的真实值

**5. 重新生成站点**

```bash
python generate.py
```

---

## 方案二：京东联盟（国内流量首选）

无需审核，注册即用。用户通过你的链接购买，佣金 1%-10%。

### 步骤

**1. 注册**
访问 [union.jd.com](https://union.jd.com)，注册京东联盟账号。

**2. 获取推广链接**
- 联盟后台 → 推广管理 → 推广商品
- 搜索你要推荐的商品
- 点击"立即推广"→ 复制短链接或完整链接

**3. 在文章 front matter 中使用**

编辑文章 `.md` 文件：

```yaml
---
title: 2026年蓝牙耳机推荐
affiliate_url: https://u.jd.com/你的推广链接
affiliate_text: 👉 去京东查看最新价格
---
```

文章底部会自动出现红色购买按钮，用户点击下单你就有佣金。

### 收入预估

| 商品类型 | 佣金比例 | 客单价 ¥300 收入 |
|---------|---------|----------------|
| 数码 3C | 1-2% | ¥3-6 |
| 家电 | 2-5% | ¥6-15 |
| 美妆 | 5-10% | ¥15-30 |
| 家居 | 3-8% | ¥9-24 |

---

## 方案三：淘宝客（阿里妈妈）

和京东联盟类似，佣金更高但链接可能不稳定。

注册 [pub.alimama.com](https://pub.alimama.com)，生成淘口令或链接，替换文章中的 `affiliate_url`。

---

## 方案四：品牌软文合作

流量到日均 500 UV 后可以考虑：

- **新榜** (newrank.cn)：接品牌投放
- **媒介盒子**：自媒体接单平台
- **直接联系品牌方**：PR 部门通常会回复

报价参考：公众号/网站 1 个 UV ≈ ¥0.3-1 元

---

## 实际收入模型

以日均 1000 UV 的好物推荐站为例：

| 来源 | 月收入（约） |
|------|------------|
| Google AdSense | ¥200-600 |
| 京东联盟佣金 | ¥300-1000 |
| 品牌软文（2篇/月） | ¥400-1000 |
| **合计** | **¥900-2600** |

---

## ⚠️ 注意事项

1. **不要自己点击广告** → 会被封号
2. **不要诱导点击**（"点一下广告支持我们"） → 违规
3. **流量来源要自然** → 刷量会被 K 号
4. **内容要原创** → 采集站现在很难过审
5. **先上线再申请** → 本地 localhost 无法申请 AdSense
