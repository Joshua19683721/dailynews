#!/usr/bin/env python3
"""Send a daily email of elementary-school digital and STEM activities."""

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime, parsedate_to_datetime
from html import escape
from html.parser import HTMLParser
import os
import re
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
MAX_ITEMS_PER_QUERY = 20
RSS_BASE = "https://news.google.com/rss/search"
EDUCATION_QUERY = (
    "intitle:(國小 OR 小學) "
    "(比賽 OR 競賽 OR 徵件 OR 甄選 OR 盃) "
    "(2026 OR 2027) "
    "(網路 OR 線上 OR 網頁 OR 電腦 OR 數位) "
    "(AI OR 人工智慧 OR 程式 OR Scratch OR 機器人 OR 創客 "
    "OR Maker OR SDGs OR 永續 OR 氣候變遷)"
)
TECH_TERMS = (
    "AI",
    "人工智慧",
    "程式",
    "Scratch",
    "機器人",
    "創客",
    "Maker",
    "SDGs",
    "永續",
    "氣候變遷",
    "網路",
    "線上",
    "網頁",
    "電腦",
    "數位",
)
DATE_PATTERN = re.compile(
    r"(?:202[67]\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?"
    r"(?:\s*(?:至|到|[-～])\s*(?:(?:202[67]\s*年)?\s*)?"
    r"\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?)?)"
    r"|(?:202[67][./-]\d{1,2}(?:[./-]\d{1,2})?)"
    r"|(?:\d{1,2}\s*月\s*\d{1,2}\s*日)"
)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _plain_text(markup):
    parser = _TextExtractor()
    parser.feed(markup)
    return " ".join(" ".join(parser.parts).split())


def _publication_date(value):
    if not value:
        return "發布時間未提供"
    try:
        return parsedate_to_datetime(value).astimezone(TAIPEI_TZ).strftime(
            "%Y-%m-%d %H:%M (台灣時間)"
        )
    except (TypeError, ValueError, OverflowError):
        return value


def fetch_activities():
    params = urllib.parse.urlencode(
        {"q": EDUCATION_QUERY, "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}
    )
    request = urllib.request.Request(
        f"{RSS_BASE}?{params}",
        headers={"User-Agent": "DailyStudentActivities/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())

    activities = []
    seen_links = set()
    for entry in root.findall("./channel/item")[:MAX_ITEMS_PER_QUERY]:
        title = (entry.findtext("title") or "").strip()
        link = (entry.findtext("link") or "").strip()
        parsed_link = urllib.parse.urlsplit(link)
        if (
            not title
            or parsed_link.scheme not in {"http", "https"}
            or not parsed_link.netloc
            or link in seen_links
        ):
            continue
        seen_links.add(link)

        source_element = entry.find("source")
        source = (
            source_element.text.strip()
            if source_element is not None and source_element.text
            else "新聞來源"
        )
        activities.append(
            {
                "title": title,
                "summary": _plain_text(entry.findtext("description") or ""),
                "link": link,
                "published": _publication_date(entry.findtext("pubDate") or ""),
                "source": source,
            }
        )
    return activities


def _activity_fields(activity):
    text = f"{activity['title']} {activity['summary']}"
    technologies = [
        term for term in TECH_TERMS if term.casefold() in text.casefold()
    ]
    dates = list(dict.fromkeys(DATE_PATTERN.findall(text)))
    return technologies, dates


def build_message(sender, activities, failures):
    now = datetime.now(TAIPEI_TZ)
    message = EmailMessage()
    message["From"] = sender
    message["To"] = RECIPIENT
    message["Date"] = format_datetime(now)
    message["Subject"] = f"國小數位與科技競賽活動整理｜{now:%Y-%m-%d}"

    plain = [
        f"國小數位與科技競賽活動整理（{now:%Y-%m-%d %H:%M} 台灣時間）",
        "",
        "搜尋條件：國小／小學競賽、徵件或甄選，聚焦 2026–2027 年網路、數位、AI、程式、創客、永續等主題。",
        "以下資訊取自新聞搜尋摘要；參賽資格、報名方式及時程請務必以主辦單位原始公告為準。",
    ]
    html = [
        f"<p>國小數位與科技競賽活動整理（{now:%Y-%m-%d %H:%M} 台灣時間）</p>",
        "<p>搜尋國小／小學競賽、徵件或甄選，聚焦 2026–2027 年網路、數位、AI、程式、創客、永續等主題。<br>"
        "以下資訊取自新聞搜尋摘要；參賽資格、報名方式及時程請務必以主辦單位原始公告為準。</p>",
    ]

    if not activities:
        no_results = "本次搜尋沒有找到符合條件的活動。"
        plain.extend(["", no_results])
        html.append(f"<p>{escape(no_results)}</p>")

    for index, activity in enumerate(activities, start=1):
        technologies, dates = _activity_fields(activity)
        technology_text = "、".join(technologies) if technologies else "請查看活動原文"
        summary = activity["summary"] or "新聞摘要未提供，請查看活動原文。"
        schedule = (
            "、".join(dates)
            if dates
            else f"摘要未提及活動日期；新聞發布時間：{activity['published']}（非競賽日期）"
        )
        plain.extend(
            [
                "",
                f"{index}. {activity['title']}",
                f"   • 科技元素：{technology_text}",
                f"   • 核心內容：{summary}",
                f"   • 競賽時程：{schedule}",
                f"   • 來源：{activity['source']}｜{activity['published']}",
                f"     {activity['link']}",
            ]
        )
        html.append(
            f"<h3>{index}. {escape(activity['title'])}</h3>"
            "<ul>"
            f"<li><strong>科技元素：</strong>{escape(technology_text)}</li>"
            f"<li><strong>核心內容：</strong>{escape(summary)}</li>"
            f"<li><strong>競賽時程：</strong>{escape(schedule)}</li>"
            f"<li><strong>來源：</strong>{escape(activity['source'])}｜"
            f"{escape(activity['published'])}<br>"
            f'<a href="{escape(activity["link"], quote=True)}">查看原始報導</a></li>'
            "</ul>"
        )

    if failures:
        plain.extend(["", "資料來源讀取狀況："])
        plain.extend(f"• {failure}" for failure in failures)
        html.append("<h3>資料來源讀取狀況</h3><ul>")
        html.extend(f"<li>{escape(failure)}</li>" for failure in failures)
        html.append("</ul>")

    message.set_content("\n".join(plain))
    message.add_alternative("\n".join(html), subtype="html")
    return message


def main():
    sender = (
        os.environ.get("GMAIL_USER") or os.environ.get("SMTP_USERNAME") or ""
    ).strip()
    app_password = (
        os.environ.get("GMAIL_APP_PASSWORD")
        or os.environ.get("SMTP_APP_PASSWORD")
        or ""
    ).replace(" ", "").strip()
    if not sender or not app_password:
        raise RuntimeError(
            "請設定 GMAIL_USER 與 GMAIL_APP_PASSWORD（或 SMTP_USERNAME 與 SMTP_APP_PASSWORD）。"
        )
    if not RECIPIENT:
        raise RuntimeError("收件地址 MAIL_TO 不可為空。")

    failures = []
    try:
        activities = fetch_activities()
    except (urllib.error.URLError, TimeoutError, ET.ParseError) as error:
        activities = []
        failures.append(f"教育活動搜尋失敗：{type(error).__name__}")

    message = build_message(sender, activities, failures)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(message)
    print(f"教育活動整理已寄出至 {RECIPIENT}；收錄 {len(activities)} 則活動。")


if __name__ == "__main__":
    main()
