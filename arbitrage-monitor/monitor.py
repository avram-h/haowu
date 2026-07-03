#!/usr/bin/env python3
"""
多平台价差监控 & 套利发现系统
- 监控加密货币在不同交易所的价格差异
- 监控电商平台商品价格波动
- 价差超过阈值自动推送通知

用法:
  python monitor.py                    # 一次性检查
  python monitor.py --daemon 60        # 每60秒检查一次（守护模式）
  python monitor.py --report           # 生成价差报告
"""

import json
import os
import sys
import time
import smtplib
import hashlib
import hmac
import base64
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from urllib.request import urlopen, Request
from urllib.error import URLError

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
HISTORY_FILE = BASE_DIR / "history.json"

# ============================================================
# 配置
# ============================================================

DEFAULT_CONFIG = {
    "monitors": {
        "crypto": {
            "enabled": True,
            "pairs": [
                {"symbol": "BTC/USDT", "threshold_pct": 0.5, "min_profit_usd": 10},
                {"symbol": "ETH/USDT", "threshold_pct": 0.5, "min_profit_usd": 5},
                {"symbol": "SOL/USDT", "threshold_pct": 1.0, "min_profit_usd": 3},
            ],
            "exchanges": ["binance", "okx", "huobi", "bybit"]
        },
        "ecommerce": {
            "enabled": True,
            "products": []  # 手动配置需要监控的商品
        }
    },
    "notifications": {
        "email": {
            "enabled": False,
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "sender": "your-email@gmail.com",
            "password": "",  # 使用应用专用密码
            "recipient": "your-email@gmail.com"
        },
        "dingtalk": {
            "enabled": False,
            "webhook_url": ""
        },
        "feishu": {
            "enabled": False,
            "webhook_url": ""
        },
        "telegram": {
            "enabled": False,
            "bot_token": "",
            "chat_id": ""
        },
        "console": {
            "enabled": True
        }
    },
    "general": {
        "check_interval_seconds": 60,
        "save_history": True
    }
}


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # 深度合并默认配置
            merged = DEFAULT_CONFIG.copy()
            for key in merged:
                if key in cfg:
                    if isinstance(merged[key], dict):
                        merged[key].update(cfg[key])
                    else:
                        merged[key] = cfg[key]
            return merged
    return DEFAULT_CONFIG


# ============================================================
# 数据源：加密货币价格
# ============================================================

class CryptoPriceFetcher:
    """从交易所 API 获取加密货币价格"""

    API_ENDPOINTS = {
        "binance": "https://api.binance.com/api/v3/ticker/price",
        "okx": "https://www.okx.com/api/v5/market/ticker",
        "huobi": "https://api.huobi.pro/market/tickers",
        "bybit": "https://api.bybit.com/v5/market/tickers",
        "gate": "https://api.gateio.ws/api/v4/spot/tickers",
        "kucoin": "https://api.kucoin.com/api/v1/market/allTickers",
    }

    @staticmethod
    def _http_get(url, headers=None):
        try:
            req = Request(url, headers=headers or {})
            req.add_header("User-Agent", "ArbitrageMonitor/1.0")
            with urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except (URLError, json.JSONDecodeError, Exception) as e:
            print(f"  ⚠️ 请求失败 {url}: {e}")
            return None

    @classmethod
    def get_price(cls, exchange, symbol):
        """获取指定交易对的美元价格"""
        fetcher = getattr(cls, f"_fetch_{exchange}", None)
        if not fetcher:
            return None

        try:
            return fetcher(symbol)
        except Exception as e:
            print(f"  ❌ {exchange} {symbol}: {e}")
            return None

    @classmethod
    def _fetch_binance(cls, symbol):
        """Binance: BTCUSDT → price"""
        sym = symbol.replace("/", "")
        data = cls._http_get(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}")
        return float(data["price"]) if data else None

    @classmethod
    def _fetch_okx(cls, symbol):
        """OKX: BTC/USDT → instId=BTC-USDT"""
        inst = symbol.replace("/", "-")
        data = cls._http_get(f"https://www.okx.com/api/v5/market/ticker?instId={inst}")
        if data and data.get("code") == "0":
            return float(data["data"][0]["last"])
        return None

    @classmethod
    def _fetch_huobi(cls, symbol):
        """火币"""
        sym = symbol.replace("/", "").lower()
        data = cls._http_get("https://api.huobi.pro/market/tickers")
        if data and data.get("status") == "ok":
            for ticker in data["data"]:
                if ticker["symbol"] == sym:
                    return float(ticker["close"])
        return None

    @classmethod
    def _fetch_bybit(cls, symbol):
        """Bybit"""
        sym = symbol.replace("/", "")
        data = cls._http_get(f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={sym}")
        if data and data.get("retCode") == 0:
            return float(data["result"]["list"][0]["lastPrice"])
        return None

    @classmethod
    def _fetch_gate(cls, symbol):
        """Gate.io"""
        sym = symbol.replace("/", "_")
        data = cls._http_get(f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={sym}")
        if data:
            return float(data[0]["last"])
        return None

    @classmethod
    def _fetch_kucoin(cls, symbol):
        """KuCoin"""
        sym = symbol.replace("/", "-")
        data = cls._http_get(f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={sym}")
        if data and data.get("code") == "200000":
            return float(data["data"]["price"])
        return None


# ============================================================
# 套利分析引擎
# ============================================================

class ArbitrageEngine:
    def __init__(self, config):
        self.config = config
        self.opportunities = []
        self.history = self._load_history()

    def _load_history(self):
        if HISTORY_FILE.exists():
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_history(self):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.history[-500:], f, ensure_ascii=False, indent=2)

    def check_crypto(self):
        """检查加密货币跨交易所价差"""
        crypto_cfg = self.config["monitors"]["crypto"]
        if not crypto_cfg["enabled"]:
            return

        exchanges = crypto_cfg["exchanges"]
        print(f"\n🔍 检查加密货币价差 (交易所: {', '.join(exchanges)})...")

        for pair in crypto_cfg["pairs"]:
            symbol = pair["symbol"]
            threshold = pair["threshold_pct"]
            min_profit = pair["min_profit_usd"]

            prices = {}
            for exchange in exchanges:
                price = CryptoPriceFetcher.get_price(exchange, symbol)
                if price:
                    prices[exchange] = price

            if len(prices) < 2:
                continue

            best_bid = min(prices, key=prices.get)
            best_ask = max(prices, key=prices.get)
            bid_price = prices[best_bid]
            ask_price = prices[best_ask]
            spread_pct = (ask_price - bid_price) / bid_price * 100

            print(f"  {symbol}: 最低 {best_bid} ${bid_price:.4f} | 最高 {best_ask} ${ask_price:.4f} | 价差 {spread_pct:.3f}%")

            if spread_pct >= threshold:
                # 假设交易 1000 USDT
                trade_amount = 1000
                coins = trade_amount / bid_price
                profit = coins * (ask_price - bid_price)

                if profit >= min_profit:
                    opp = {
                        "type": "crypto",
                        "symbol": symbol,
                        "buy_exchange": best_bid,
                        "sell_exchange": best_ask,
                        "buy_price": round(bid_price, 4),
                        "sell_price": round(ask_price, 4),
                        "spread_pct": round(spread_pct, 3),
                        "estimated_profit": round(profit, 2),
                        "timestamp": datetime.now().isoformat(),
                    }
                    self.opportunities.append(opp)
                    self._alert(opp)

    def _alert(self, opportunity):
        """发送通知"""
        if opportunity["type"] == "crypto":
            msg = (
                f"🚨 套利机会！\n"
                f"币种: {opportunity['symbol']}\n"
                f"买入: {opportunity['buy_exchange']} @ ${opportunity['buy_price']}\n"
                f"卖出: {opportunity['sell_exchange']} @ ${opportunity['sell_price']}\n"
                f"价差: {opportunity['spread_pct']}%\n"
                f"预估利润(1000U): ${opportunity['estimated_profit']}\n"
                f"时间: {opportunity['timestamp']}"
            )

        print(f"\n{'='*50}")
        print(msg)
        print(f"{'='*50}\n")

        # 保存历史
        self.history.append(opportunity)
        self._save_history()

        # 发送各类通知
        self._send_notifications(msg)

    def _send_notifications(self, message):
        """多渠道通知"""
        notify_cfg = self.config["notifications"]

        # 钉钉
        if notify_cfg.get("dingtalk", {}).get("enabled"):
            self._send_dingtalk(notify_cfg["dingtalk"]["webhook_url"], message)

        # 飞书
        if notify_cfg.get("feishu", {}).get("enabled"):
            self._send_feishu(notify_cfg["feishu"]["webhook_url"], message)

        # Telegram
        if notify_cfg.get("telegram", {}).get("enabled"):
            self._send_telegram(notify_cfg["telegram"], message)

        # 邮件
        if notify_cfg.get("email", {}).get("enabled"):
            self._send_email(notify_cfg["email"], message)

    @staticmethod
    def _send_dingtalk(webhook_url, message):
        """钉钉机器人通知"""
        payload = json.dumps({
            "msgtype": "text",
            "text": {"content": message}
        }).encode()
        try:
            req = Request(webhook_url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            urlopen(req, timeout=5)
            print("  ✅ 钉钉通知已发送")
        except Exception as e:
            print(f"  ❌ 钉钉通知失败: {e}")

    @staticmethod
    def _send_feishu(webhook_url, message):
        """飞书机器人通知"""
        payload = json.dumps({
            "msg_type": "text",
            "content": {"text": message.replace("\n", "\\n")}
        }).encode()
        try:
            req = Request(webhook_url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            urlopen(req, timeout=5)
            print("  ✅ 飞书通知已发送")
        except Exception as e:
            print(f"  ❌ 飞书通知失败: {e}")

    @staticmethod
    def _send_telegram(cfg, message):
        """Telegram Bot 通知"""
        url = f"https://api.telegram.org/bot{cfg['bot_token']}/sendMessage"
        payload = json.dumps({
            "chat_id": cfg["chat_id"],
            "text": message,
            "parse_mode": "HTML"
        }).encode()
        try:
            req = Request(url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            urlopen(req, timeout=5)
            print("  ✅ Telegram 通知已发送")
        except Exception as e:
            print(f"  ❌ Telegram 通知失败: {e}")

    @staticmethod
    def _send_email(cfg, message):
        """邮件通知"""
        try:
            msg = MIMEText(message, "plain", "utf-8")
            msg["Subject"] = "🚨 套利机会提醒"
            msg["From"] = cfg["sender"]
            msg["To"] = cfg["recipient"]

            server = smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"])
            server.starttls()
            server.login(cfg["sender"], cfg["password"])
            server.sendmail(cfg["sender"], [cfg["recipient"]], msg.as_string())
            server.quit()
            print("  ✅ 邮件通知已发送")
        except Exception as e:
            print(f"  ❌ 邮件通知失败: {e}")

    def generate_report(self):
        """生成价差分析报告"""
        if not self.history:
            print("\n📊 暂无历史记录")
            return

        print("\n" + "=" * 60)
        print("📊 套利监控报告")
        print("=" * 60)

        crypto_ops = [h for h in self.history if h["type"] == "crypto"]
        if crypto_ops:
            print(f"\n🔗 加密货币套利机会: {len(crypto_ops)} 条")
            for op in crypto_ops[-10:]:
                print(f"  {op['symbol']}: {op['buy_exchange']}→{op['sell_exchange']} "
                      f"价差 {op['spread_pct']}% 利润 ${op['estimated_profit']}")

        total_profit = sum(op.get("estimated_profit", 0) for op in self.history)
        print(f"\n💰 潜在总利润: ${total_profit:.2f}")
        print(f"📅 监控开始: {self.history[0]['timestamp'][:10] if self.history else 'N/A'}")
        print("=" * 60)

    def run_once(self):
        """执行一次检查"""
        print(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 50)
        self.check_crypto()
        if not self.opportunities:
            print("\n📭 当前未发现套利机会")

    def run_daemon(self, interval):
        """守护进程模式"""
        print(f"\n🔄 启动守护模式，每 {interval} 秒检查一次...")
        print("按 Ctrl+C 停止\n")

        try:
            while True:
                self.run_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\n👋 监控已停止")
            self.generate_report()


# ============================================================
# 电商价格监控（京东/淘宝价格变动）
# ============================================================

class EcommerceMonitor:
    """监控电商平台商品价格"""

    @staticmethod
    def add_product(url, name="", platform="jd"):
        """添加监控商品"""
        config = load_config()
        products = config["monitors"]["ecommerce"]["products"]
        product = {
            "url": url,
            "name": name,
            "platform": platform,
            "added_at": datetime.now().isoformat(),
            "price_history": []
        }
        products.append(product)

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"  ✅ 已添加监控: {name or url}")

    @staticmethod
    def check_price(product):
        """检查单个商品价格（示例）"""
        # 注：爬取电商网站存在反爬机制，此处提供框架
        # 实际使用时建议：
        # 1. 使用官方 API（京东联盟、淘宝客等）
        # 2. 或使用第三方比价 API（慢慢买等）
        print(f"  🔍 检查: {product.get('name', product['url'])}")
        # 价格获取逻辑需根据实际 API 实现
        return None


# ============================================================
# 主程序
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="多平台价差监控系统")
    parser.add_argument("--daemon", type=int, metavar="SECONDS",
                        help="守护模式，每隔 N 秒检查")
    parser.add_argument("--report", action="store_true",
                        help="生成历史报告")
    parser.add_argument("--add-product", type=str, metavar="URL",
                        help="添加电商商品监控")
    parser.add_argument("--init-config", action="store_true",
                        help="初始化配置文件")

    args = parser.parse_args()

    # 初始化配置
    if args.init_config or not CONFIG_FILE.exists():
        if not CONFIG_FILE.exists():
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
            print(f"✅ 配置文件已创建: {CONFIG_FILE}")
            print("请编辑 config.json 配置通知方式（钉钉/飞书/Telegram/邮件）")

    config = load_config()
    engine = ArbitrageEngine(config)

    if args.add_product:
        EcommerceMonitor.add_product(args.add_product)
        return

    if args.report:
        engine.generate_report()
        return

    if args.daemon:
        engine.run_daemon(args.daemon)
    else:
        engine.run_once()


if __name__ == "__main__":
    main()
