#!/usr/bin/env python3
"""Send a daily Traditional Chinese Penghu and student-activities briefing."""

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime, parsedate_to_datetime
from html import escape
import os
import smtplib
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


TAIPEI_TZ = timezone(timedelta(hours=8))
RECIPIENT = (
    os.environ.get("MAIL_TO")
    or os.environ.get("EMAIL_TO")
    or "wdtung@gmail.com"
)
MAX_ITEMS_PER_QUERY = 5
RSS_BASE = "https://news.google.com/rss/search"


def build_queries():
    return (
        ("花火節日期與公告", "澎湖國際海上花火節 2027 日期 公告"),
        ("花火節相關消息", "澎湖花火節 2027"),
        (
            "官方網站上的 2027 花火節資訊",
            "site:penghu.gov.tw 2027 花火節 OR "
            "site:penghu-nsa.gov.tw 2027 花火節",
        ),
        ("澎湖旅遊、美食、住宿與景點", "澎湖旅遊 美食 住宿 景點"),
        ("澎湖租汽機車與優惠", "澎湖 租汽車 租機車 優惠"),
        (
            "教育活動｜國小網路／數位競賽（2026–2027）",
            "intitle:(國小 OR 小學) "
            "(比賽 OR 競賽 OR 徵件 OR 甄選 OR 盃) "
            "(2026 OR 2027) "
            "(網路 OR 線上 OR 網頁 OR 電腦 OR 數位)",
        ),
    )


def fetch_news(query):
    params = urllib.parse.urlencode(
        {"q": query, "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}
    )
    request = urllib.request.Request(
        f"{RSS_BASE}?{params}",
        headers={"User-Agent": "PenghuDailyBriefing/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())

    items = []
    for entry in root.findall("./channel/item")[:MAX_ITEMS_PER_QUERY]:
        title = (entry.findtext("title") or "").strip()
        link = (entry.findtext("link") or "").strip()
        parsed_link = urllib.parse.urlsplit(link)
        if (
            not title
            or parsed_link.scheme not in {"http", "https"}
            or not parsed_link.netloc
        ):
            continue

        published = (entry.findtext("pubDate") or "").strip()
        try:
            published = parsedate_to_datetime(published).astimezone(TAIPEI_TZ).strftime(
                "%Y-%m-%d %H:%M (台灣時間)"
            )
        except (TypeError, ValueError, OverflowError):
            published = published or "發布時間未提供"

        source_element = entry.find("source")
        source = (
            source_element.text.strip()
            if source_element is not None and source_element.text
            else "新聞來源"
        )
        items.append(
            {
                "title": title,
                "link": link,
                "published": published,
                "source": source,
            }
        )
    return items


def collect_news():
    sections = []
    failures = []
    seen_links = set()
    for heading, query in build_queries():
        try:
            results = fetch_news(query)
        except (urllib.error.URLError, TimeoutError, ET.ParseError) as error:
            failures.append(f"{heading}：{type(error).__name__}")
            sections.append((heading, []))
            continue

        unique_items = []
        for item in results:
            if item["link"] not in seen_links:
                seen_links.add(item["link"])
                unique_items.append(item)
        sections.append((heading, unique_items))

    return sections, failures


def build_message(sender, sections, failures):
    now = datetime.now(TAIPEI_TZ)
    message = EmailMessage()
    message["From"] = sender
    message["To"] = RECIPIENT
    message["Date"] = format_datetime(now)
    message["Subject"] = f"澎湖每日資訊整理｜{now:%Y-%m-%d}"

    plain = [
        f"澎湖每日資訊整理（{now:%Y-%m-%d %H:%M} 台灣時間）",
        "",
        "新聞來自 Google News RSS 搜尋，請開啟原文核對；搜尋結果不一定完整。",
        "",
        "【3 天 2 夜行程靈感】",
        "第 1 天：抵達馬公、入住市區，可安排中央老街、天后宮與在地小吃；花火節場次依當年度官方公告安排。",
        "第 2 天：依天候與交通安排北環或南環景點；租車前確認駕照、保險、費用及取還車時間。",
        "第 3 天：馬公市區採買伴手禮，預留交通與候船／候機時間後返程。",
        "",
        "【住宿與預算提醒】",
        "住宿可比較馬公市區與景點周邊民宿，預訂前確認交通、房型、取消規則與入住時間。交通、住宿、餐飲、門票及租車費用會隨出發地、日期與需求改變；比價時確認優惠期限、押金與保險。",
        "",
        "【教育活動提醒】",
        "搜尋澎湖縣國小學生近期與即將開始活動。請開啟原始公告核對適用年級、活動日期、報名期限，以及是否明確要求使用澎湖縣教育雲端帳號；搜尋結果不一定完整。",
    ]
    html = [
        f"<p>澎湖每日資訊整理（{now:%Y-%m-%d %H:%M} 台灣時間）</p>",
        "<p>新聞來自 Google News RSS 搜尋，請開啟原文核對；搜尋結果不一定完整。</p>",
        "<h2>3 天 2 夜行程靈感</h2>",
        "<ol>"
        "<li>抵達馬公、入住市區，可安排中央老街、天后宮與在地小吃；花火節場次依當年度官方公告安排。</li>"
        "<li>依天候與交通安排北環或南環景點；租車前確認駕照、保險、費用及取還車時間。</li>"
        "<li>馬公市區採買伴手禮，預留交通與候船／候機時間後返程。</li>"
        "</ol>",
        "<h2>住宿與預算提醒</h2>",
        "<p>住宿可比較馬公市區與景點周邊民宿，預訂前確認交通、房型、取消規則與入住時間。交通、住宿、餐飲、門票及租車費用會隨出發地、日期與需求改變；比價時確認優惠期限、押金與保險。</p>",
        "<h2>教育活動提醒</h2>",
        "<p>搜尋澎湖縣國小學生近期與即將開始活動。請開啟原始公告核對適用年級、活動日期、報名期限，以及是否明確要求使用澎湖縣教育雲端帳號；搜尋結果不一定完整。</p>",
    ]

    for heading, items in sections:
        plain.extend(["", f"【{heading}】"])
        html.append(f"<h2>{escape(heading)}</h2>")
        if not items:
            no_result = (
                "本次搜尋沒有找到可引用的結果；這不代表沒有公告，請查閱官方網站。"
                if "2027" in heading
                else "本次搜尋沒有找到可引用的結果；這不代表沒有相關活動或消息。"
            )
            plain.append(no_result)
            html.append(f"<p>{escape(no_result)}</p>")
            continue

        for item in items:
            plain.append(
                f"- {item['title']}（{item['source']}；{item['published']}）\n"
                f"  {item['link']}"
            )
        html_items = "".join(
            "<li>"
            f'<a href="{escape(item["link"], quote=True)}">{escape(item["title"])}</a>'
            f" — {escape(item['source'])}；{escape(item['published'])}"
            "</li>"
            for item in items
        )
        html.append(f"<ul>{html_items}</ul>")

    if failures:
        plain.extend(["", "【資料來源讀取狀況】"])
        plain.extend(f"- {failure}" for failure in failures)
        html.append("<h2>資料來源讀取狀況</h2><ul>")
        html.extend(f"<li>{escape(failure)}</li>" for failure in failures)
        html.append("</ul>")

    plain.extend(
        [
            "",
            "交通、住宿、營業時間、優惠及活動內容可能變動，請以官方公告及店家最新資訊為準。",
        ]
    )
    html.append(
        "<p>交通、住宿、營業時間、優惠及活動內容可能變動，"
        "請以官方公告及店家最新資訊為準。</p>"
    )
    message.set_content("\n".join(plain))
    message.add_alternative("\n".join(html), subtype="html")
    return message


def main():
    gmail_user = (
        os.environ.get("GMAIL_USER") or os.environ.get("SMTP_USERNAME") or ""
    ).strip()
    app_password = (
        os.environ.get("GMAIL_APP_PASSWORD")
        or os.environ.get("SMTP_APP_PASSWORD")
        or ""
    ).replace(" ", "").strip()
    if not gmail_user or not app_password:
        raise RuntimeError(
            "請設定 GMAIL_USER 與 GMAIL_APP_PASSWORD（或 SMTP_USERNAME 與 SMTP_APP_PASSWORD）。"
        )
    if not RECIPIENT:
        raise RuntimeError("收件地址 MAIL_TO 不可為空。")

    sections, failures = collect_news()
    message = build_message(gmail_user, sections, failures)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(gmail_user, app_password)
        smtp.send_message(message)

    result_count = sum(len(items) for _, items in sections)
    print(f"每日澎湖與教育活動整理已寄出至 {RECIPIENT}；收錄 {result_count} 則資訊。")


if __name__ == "__main__":
    main()
