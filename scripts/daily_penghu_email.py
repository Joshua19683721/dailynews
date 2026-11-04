#!/usr/bin/env python3
"""Send a daily Traditional Chinese Penghu travel digest using Google News RSS."""

from datetime import datetime
from email.message import EmailMessage
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

QUERIES = [
    ("花火節日期與公告", "澎湖國際海上花火節 2027 日期 公告"),
    ("花火節相關消息", "澎湖花火節 2027"),
    ("吃住玩推薦", "澎湖旅遊 美食 住宿 景點"),
    ("租汽機車優惠", "澎湖 租汽車 租機車 優惠"),
]
RSS_BASE = "https://news.google.com/rss/search"

def fetch_news():
    items = []
    seen = set()
    for category, query in QUERIES:
        params = urllib.parse.urlencode({
            "q": query,
            "hl": "zh-TW",
            "gl": "TW",
            "ceid": "TW:zh-Hant",
        })
        request = urllib.request.Request(
            f"{RSS_BASE}?{params}",
            headers={"User-Agent": "dailynews Penghu digest/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                root = ET.fromstring(response.read())
            for entry in root.findall("./channel/item")[:5]:
                title = (entry.findtext("title") or "").strip()
                link = (entry.findtext("link") or "").strip()
                if not title or not link or link in seen:
                    continue
                seen.add(link)
                pub_date = entry.findtext("pubDate") or ""
                try:
                    date_label = parsedate_to_datetime(pub_date).strftime("%Y-%m-%d")
                except (TypeError, ValueError):
                    date_label = pub_date
                source = entry.find("source")
                source_name = source.text.strip() if source is not None and source.text else "新聞來源"
                items.append({
                    "category": category,
                    "title": title,
                    "link": link,
                    "date": date_label,
                    "source": source_name,
                })
        except (urllib.error.URLError, TimeoutError, ET.ParseError) as exc:
            print(f"RSS query failed ({category}): {exc}", file=sys.stderr)
    return items

def make_email(items):
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"澎湖旅遊每日情報｜{today}｜2027 花火節・4–7月規劃"
    lines = [
        f"澎湖旅遊每日情報（{today}）",
        "旅遊月份：2027 年 4–7 月｜行程參考：3 天 2 夜（可依需求調整）",
        "",
        "【花火節日期與公告】",
        "花火節日期、場次及交通管制請以澎湖縣政府與主辦單位最新公告為準。以下新聞僅供追蹤，尚未看到公告不代表尚未公布。",
        "",
    ]

    if items:
        for item in items:
            lines.append(f"【{item['category']}】{item['title']}（{item['source']}，{item['date']}）")
            lines.append(item["link"])
            lines.append("")
    else:
        lines.extend(["今天未能取得新聞 RSS 資料，請稍後再查詢官方公告。", ""])

    lines.extend([
        "【3 天 2 夜行程靈感】",
        "第 1 天：抵達馬公、入住市區，逛中央老街與天后宮，品嚐在地小吃；晚上依當年度公告前往花火節場次。",
        "第 2 天：安排北環或南環景點一日遊，沿途依開放狀況選擇景點與海鮮餐；租車前先確認駕照、保險、油資與取還車時間。",
        "第 3 天：馬公市區採買伴手禮，預留交通與候船／候機時間後返程。船班、航班及景點營運請出發前確認。",
        "",
        "【吃住玩與預算提醒】",
        "住宿可比較馬公市區（交通與用餐方便）及景點周邊民宿；餐食可安排海鮮、在地小吃並先查營業日。預算依出發地、交通方式、住宿等級、花火節日期和租車天數差異很大；比價時分開核對交通、住宿、餐飲、門票及租車費用，並確認優惠期限、押金、保險與取消規則。",
        "",
        "資訊來源為 Google News RSS 搜尋結果，內容及優惠可能變動，請點開原文並向店家／官方單位核實。",
    ])

    return subject, "\n".join(lines)

def main():
    username = os.environ.get("SMTP_USERNAME", "").strip()
    app_password = os.environ.get("SMTP_APP_PASSWORD", "").replace(" ", "").strip()
    recipient = os.environ.get("EMAIL_TO", "").strip()

    if not username or not app_password or not recipient:
        raise SystemExit("Missing SMTP_USERNAME, SMTP_APP_PASSWORD, or EMAIL_TO environment variable.")

    subject, body = make_email(fetch_news())
    message = EmailMessage()
    message["From"] = username
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=30) as server:
        server.login(username, app_password)
        server.send_message(message)

    print(f"Daily Penghu digest sent to {recipient}.")

if __name__ == "__main__":
    main()
