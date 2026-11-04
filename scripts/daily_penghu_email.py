#!/usr/bin/env python3
"""Fetch a Penghu and student-activity briefing, then send it via Gmail."""

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
RECIPIENT = os.environ.get("MAIL_TO", "wdtung@gmail.com")
MAX_ITEMS_PER_QUERY = 5
FEEDS = (
    (
        "澎湖旅遊與民宿",
        "澎湖旅遊 OR 澎湖民宿 OR 澎湖住宿",
    ),
    (
        "2027 澎湖花火節",
        "2027 澎湖花火節 OR 2027 澎湖國際海上花火節",
    ),
    (
        "官方網站上的 2027 花火節資訊",
        "site:penghu.gov.tw 2027 花火節 OR "
        "site:penghu-nsa.gov.tw 2027 花火節",
    ),
)
EDUCATION_FEEDS = (
    (
        "澎湖縣教育雲端帳號｜國小學生近期與即將開始的活動",
        '"澎湖縣教育雲端帳號" 活動 國小 報名',
    ),
    (
        "澎湖縣教育雲／學生帳號｜近期活動與競賽",
        '澎湖縣 教育雲 學生帳號 國小 活動 OR 競賽',
    ),
    (
        "澎湖縣官方教育與學校網站｜學生近期活動",
        '(site:penghu.gov.tw OR site:ph.edu.tw) 澎湖 國小 學生 活動 報名',
    ),
    (
        "澎湖縣教育雲端帳號｜近期公告的即將開始活動",
        '"澎湖縣教育雲端帳號" (即將 OR 報名 OR 開始 OR 活動)',
    ),
)


def fetch_feed(query):
    """Return parsed entries from one Google News RSS search."""
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "PenghuDailyBriefing/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())

    items = []
    for item in root.findall("./channel/item")[:MAX_ITEMS_PER_QUERY]:
        title = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        parsed_link = urllib.parse.urlsplit(link)
        if not title or parsed_link.scheme not in {"http", "https"} or not parsed_link.netloc:
            continue

        published = item.findtext("pubDate", default="").strip()
        source_element = item.find("source")
        source = source_element.text.strip() if source_element is not None and source_element.text else ""

        if published:
            try:
                published = parsedate_to_datetime(published).astimezone(TAIPEI_TZ).strftime(
                    "%Y-%m-%d %H:%M (台灣時間)"
                )
            except (TypeError, ValueError, OverflowError):
                pass

        items.append(
            {
                "title": title,
                "link": link,
                "published": published or "發布時間未提供",
                "source": source or "來源未提供",
            }
        )
    return items


def collect_briefing():
    sections = []
    failures = []
    seen_links = set()
    recent_cutoff = (datetime.now(TAIPEI_TZ).date() - timedelta(days=30)).isoformat()
    upcoming_cutoff = (datetime.now(TAIPEI_TZ).date() - timedelta(days=90)).isoformat()
    feeds = FEEDS + tuple(
        (heading, f"{query} after:{recent_cutoff}")
        for heading, query in EDUCATION_FEEDS[:3]
    )
    feeds += (
        (
            EDUCATION_FEEDS[3][0],
            f"{EDUCATION_FEEDS[3][1]} after:{upcoming_cutoff}",
        ),
    )

    for heading, query in feeds:
        try:
            items = fetch_feed(query)
        except (urllib.error.URLError, TimeoutError, ET.ParseError) as error:
            failures.append(f"{heading}：{type(error).__name__}")
            sections.append((heading, []))
            continue

        unique_items = []
        for item in items:
            if item["link"] not in seen_links:
                seen_links.add(item["link"])
                unique_items.append(item)
        sections.append((heading, unique_items))

    return sections, failures


def build_message(sender, sections, failures):
    now = datetime.now(TAIPEI_TZ)
    message = EmailMessage()
    message["Subject"] = f"澎湖每日資訊整理｜{now:%Y-%m-%d}"
    message["From"] = sender
    message["To"] = RECIPIENT
    message["Date"] = format_datetime(now)

    plain_sections = [
        f"澎湖每日資訊整理（{now:%Y-%m-%d %H:%M} 台灣時間）",
        "",
        "以下內容來自 Google News RSS 搜尋，請點開來源確認詳情。",
        "教育活動請以原始公告核對適用對象、活動日期、報名期限及是否要求使用澎湖縣教育雲端帳號；搜尋結果不一定完整。",
    ]
    html_sections = [
        f"<p>澎湖每日資訊整理（{now:%Y-%m-%d %H:%M} 台灣時間）</p>",
        "<p>以下內容來自 Google News RSS 搜尋，請點開來源確認詳情。</p>",
        "<p>教育活動請以原始公告核對適用對象、活動日期、報名期限及是否要求使用澎湖縣教育雲端帳號；搜尋結果不一定完整。</p>",
    ]

    for heading, items in sections:
        plain_sections.extend(["", heading])
        html_sections.append(f"<h2>{escape(heading)}</h2>")
        if not items:
            no_result = (
                "本次搜尋沒有找到可引用的結果；這不代表沒有公告，"
                "請以官方網站最新資訊為準。"
                if "2027" in heading
                else "近期期限內沒有找到可引用的活動消息；這不代表沒有活動，請查閱官方公告。"
                if "教育雲" in heading or "教育與學校網站" in heading
                else "本次搜尋沒有找到可引用的結果。"
            )
            plain_sections.append(no_result)
            html_sections.append(f"<p>{escape(no_result)}</p>")
            continue

        plain_sections.extend(
            f"- {item['title']}（{item['source']}；{item['published']}）\n  {item['link']}"
            for item in items
        )
        html_items = "".join(
            "<li>"
            f'<a href="{escape(item["link"], quote=True)}">{escape(item["title"])}</a>'
            f" — {escape(item['source'])}；{escape(item['published'])}"
            "</li>"
            for item in items
        )
        html_sections.append(f"<ul>{html_items}</ul>")

    if failures:
        plain_sections.extend(["", "資料來源讀取狀況"])
        plain_sections.extend(f"- {failure}" for failure in failures)
        html_sections.append("<h2>資料來源讀取狀況</h2><ul>")
        html_sections.extend(f"<li>{escape(failure)}</li>" for failure in failures)
        html_sections.append("</ul>")

    message.set_content("\n".join(plain_sections))
    message.add_alternative("\n".join(html_sections), subtype="html")
    return message


def main():
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not gmail_user or not app_password:
        raise RuntimeError("請在 GitHub Actions secrets 設定 GMAIL_USER 與 GMAIL_APP_PASSWORD。")
    if not RECIPIENT:
        raise RuntimeError("收件地址 MAIL_TO 不可為空。")

    sections, failures = collect_briefing()
    message = build_message(gmail_user, sections, failures)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(gmail_user, app_password)
        smtp.send_message(message)

    result_count = sum(len(items) for _, items in sections)
    print(f"每日整理已寄出至 {RECIPIENT}；收錄 {result_count} 則資訊。")


if __name__ == "__main__":
    main()
