#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generátor RSS feedu pro blog na mincmistr.cz (Shoptet).

Skript stáhne výpis článků z blogu (včetně stránkování přes /blog/strana-N/),
z každé karty vytáhne titulek, URL, datum publikace a perex, a vygeneruje
validní RSS 2.0 XML soubor (feed.xml).

Python 3.8+

Závislosti:
    pip install requests beautifulsoup4 lxml

Použití:
    python3 generate_rss.py
    python3 generate_rss.py --output /var/www/html/feed.xml --limit 20

Pro automatizaci (cron):
    0 */6 * * * /usr/bin/python3 /cesta/ke/generate_rss.py
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup

# ============================================================
# KONFIGURACE — uprav podle potřeby
# ============================================================
CONFIG = {
    "base_url": "https://www.mincmistr.cz",
    "blog_url": "https://www.mincmistr.cz/blog/",
    # Vzor pro stránkování — {n} bude nahrazeno číslem stránky (2, 3, ...)
    "pagination_url": "https://www.mincmistr.cz/blog/strana-{n}/",
    "feed_title": "Mincmistr.cz — Blog",
    "feed_description": (
        "Články o mincích, bankovkách, historii a sběratelství "
        "z blogu Mincmistr.cz."
    ),
    "feed_language": "cs-cz",
    "output_path": "feed.xml",
    "limit": 20,
    "user_agent": (
        "Mozilla/5.0 (compatible; MincmistrRSSBot/1.0; "
        "+https://www.mincmistr.cz)"
    ),
    "request_timeout": 20,
    "delay_between_requests": 0.3,
    # Maximální počet stránek stránkování, které načteme
    "max_pages": 4,
}

# Selektor karty článku v Shoptet blog listingu (mincmistr.cz šablona)
CARD_SELECTOR = "div.news-item"
# Fallback selektory, kdyby Shoptet upravil šablonu
CARD_FALLBACK_SELECTORS = [
    "article.blog-item",
    "div.blog-item",
    "div.article-box",
    "div.blog-article",
    "div.blog-post",
]

# ============================================================


def _guess_image_mime(url: str) -> str:
    """Odhadne MIME typ z koncovky URL."""
    u = url.lower().split("?")[0]
    if u.endswith(".png"):
        return "image/png"
    if u.endswith(".jpg") or u.endswith(".jpeg"):
        return "image/jpeg"
    if u.endswith(".webp"):
        return "image/webp"
    if u.endswith(".gif"):
        return "image/gif"
    if u.endswith(".svg"):
        return "image/svg+xml"
    return "image/jpeg"


@dataclass
class Article:
    title: str
    link: str
    pub_date: datetime | None
    description: str
    image_url: str = ""

    def to_rss_item(self) -> str:
        parts = ["    <item>"]
        parts.append(f"      <title>{escape(self.title)}</title>")
        parts.append(f"      <link>{escape(self.link)}</link>")
        parts.append(
            f"      <guid isPermaLink=\"true\">{escape(self.link)}</guid>"
        )
        if self.pub_date is not None:
            dt = self.pub_date
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            parts.append(f"      <pubDate>{format_datetime(dt)}</pubDate>")

        # Description: pokud máme obrázek, vlož ho jako HTML <img> na začátek
        # (wrapped v CDATA, aby čtečky parsovaly HTML). Jinak plain text.
        if self.image_url or self.description:
            if self.image_url:
                safe_img = self.image_url.replace("]]>", "]]]]><![CDATA[>")
                safe_desc = (self.description or "").replace(
                    "]]>", "]]]]><![CDATA[>"
                )
                inner = (
                    f'<img src="{safe_img}" alt="" />'
                    f'<p>{safe_desc}</p>' if safe_desc else
                    f'<img src="{safe_img}" alt="" />'
                )
                parts.append(
                    f"      <description><![CDATA[{inner}]]></description>"
                )
            else:
                parts.append(
                    f"      <description>{escape(self.description)}"
                    f"</description>"
                )

        # Enclosure (standardní způsob, jak RSS přibalí soubor)
        if self.image_url:
            mime = _guess_image_mime(self.image_url)
            parts.append(
                f'      <enclosure url="{escape(self.image_url)}" '
                f'length="0" type="{mime}" />'
            )
            # Media:content (Media RSS namespace) — širší podpora ve čtečkách
            parts.append(
                f'      <media:content url="{escape(self.image_url)}" '
                f'medium="image" type="{mime}" />'
            )
            # Media:thumbnail — některé čtečky preferují
            parts.append(
                f'      <media:thumbnail url="{escape(self.image_url)}" />'
            )

        parts.append("    </item>")
        return "\n".join(parts)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": CONFIG["user_agent"],
            "Accept-Language": "cs,en;q=0.8",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            ),
        }
    )
    return s


def fetch(session: requests.Session, url: str) -> str:
    resp = session.get(url, timeout=CONFIG["request_timeout"])
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def parse_czech_date(text: str) -> datetime | None:
    """Parsuje různé formáty data používané Shoptetem."""
    text = (text or "").strip()
    if not text:
        return None
    # Shoptet používá: "2026-04-14 16:20:43" v datetime atributu
    m = re.search(
        r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?", text
    )
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        h = int(m.group(4)) if m.group(4) else 0
        mi = int(m.group(5)) if m.group(5) else 0
        s = int(m.group(6)) if m.group(6) else 0
        try:
            return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
        except ValueError:
            pass
    # České D.M.YYYY
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d, tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def clean_text(text: str, max_len: int = 500) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "…"
    return text


def extract_cards(soup: BeautifulSoup):
    """Najde karty článků. Zkusí primární a pak fallback selektory."""
    cards = soup.select(CARD_SELECTOR)
    if cards:
        return cards
    for sel in CARD_FALLBACK_SELECTORS:
        cards = soup.select(sel)
        if cards:
            return cards
    return []


def parse_card(card, base_url: str) -> Article | None:
    # Titulek a odkaz — Shoptet používá <a class="title">, fallback na jiné
    title_el = (
        card.select_one("a.title")
        or card.select_one("a[data-testid='textArticleTitle']")
        or card.select_one("h2 a")
        or card.select_one("h3 a")
    )
    if title_el is None:
        return None
    link = title_el.get("href") or ""
    title = clean_text(title_el.get_text() or "", max_len=300)
    if not link or not title:
        return None
    link = urljoin(base_url, link)
    if re.search(r"/blog/?$", link) or "strana-" in link:
        return None

    # Datum — <time datetime="2026-04-14 16:20:43">
    pub_date = None
    time_el = card.select_one("time")
    if time_el is not None:
        pub_date = parse_czech_date(
            time_el.get("datetime") or time_el.get_text()
        )

    # Perex — <div class="description"><p>...</p></div>
    perex = ""
    desc_el = (
        card.select_one("div.description")
        or card.select_one(".perex")
        or card.select_one("p")
    )
    if desc_el is not None:
        perex = clean_text(desc_el.get_text(), max_len=500)

    # Hero obrázek — <div class="image"><img src="..." width="800">
    # Shoptet má lazy-loading: u článků kromě prvního je v `src` SVG
    # placeholder a skutečná URL v `data-src`. Preferujeme data-src, pak src.
    image_url = ""
    img_el = (
        card.select_one("div.image img")
        or card.select_one("a.image img")
        or card.select_one("img")
    )
    if img_el is not None:
        src = (
            img_el.get("data-src")
            or img_el.get("data-lazy-src")
            or img_el.get("data-original")
            or img_el.get("src")
            or ""
        )
        # Přeskoč data: URI (placeholdery)
        if src and not src.startswith("data:"):
            image_url = urljoin(base_url, src)

    return Article(
        title=title,
        link=link,
        pub_date=pub_date,
        description=perex,
        image_url=image_url,
    )


def fetch_page_articles(
    session: requests.Session, url: str, verbose: bool = False
) -> list[Article]:
    """Stáhne jednu stránku výpisu a vrátí seznam článků z ní."""
    if verbose:
        print(f"  stahuji: {url}")
    html = fetch(session, url)
    soup = BeautifulSoup(html, "lxml")
    cards = extract_cards(soup)
    if verbose:
        print(f"    karet na stránce: {len(cards)}")
    articles = []
    for card in cards:
        art = parse_card(card, CONFIG["base_url"])
        if art is not None:
            articles.append(art)
    return articles


def build_rss(articles: list[Article]) -> str:
    now = format_datetime(datetime.now(tz=timezone.utc))
    items_xml = "\n".join(a.to_rss_item() for a in articles)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:media="http://search.yahoo.com/mrss/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{escape(CONFIG['feed_title'])}</title>
    <link>{escape(CONFIG['blog_url'])}</link>
    <description>{escape(CONFIG['feed_description'])}</description>
    <language>{CONFIG['feed_language']}</language>
    <lastBuildDate>{now}</lastBuildDate>
    <generator>generate_rss.py (mincmistr.cz)</generator>
    <atom:link href="{escape(CONFIG['blog_url'])}feed.xml" rel="self" type="application/rss+xml" />
{items_xml}
  </channel>
</rss>
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generátor RSS feedu pro blog mincmistr.cz"
    )
    parser.add_argument("--output", "-o", default=CONFIG["output_path"])
    parser.add_argument("--limit", "-n", type=int, default=CONFIG["limit"])
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    session = make_session()

    all_articles: list[Article] = []
    seen: set[str] = set()

    # Stáhni první stránku + další podle potřeby, až dosáhneme limitu
    for page_num in range(1, CONFIG["max_pages"] + 1):
        if page_num == 1:
            url = CONFIG["blog_url"]
        else:
            url = CONFIG["pagination_url"].format(n=page_num)

        print(f"▶ Stránka {page_num}: {url}")
        try:
            page_articles = fetch_page_articles(session, url, args.verbose)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                print(f"  stránka neexistuje, končím stránkování")
                break
            raise
        except requests.RequestException as e:
            print(f"  ❌ chyba stahování: {e}", file=sys.stderr)
            break

        added = 0
        for art in page_articles:
            if art.link in seen:
                continue
            seen.add(art.link)
            all_articles.append(art)
            added += 1

        print(f"  nových článků: {added} (celkem: {len(all_articles)})")

        if len(all_articles) >= args.limit:
            break
        if added == 0:
            break
        if CONFIG["delay_between_requests"] > 0:
            time.sleep(CONFIG["delay_between_requests"])

    if not all_articles:
        print(
            "❌ Žádné články se nepodařilo naparsovat. "
            "Zkontroluj selektor CARD_SELECTOR.",
            file=sys.stderr,
        )
        return 2

    # Seřaď od nejnovějšího
    all_articles.sort(
        key=lambda a: a.pub_date or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    # Ořež na limit
    all_articles = all_articles[: args.limit]

    rss_xml = build_rss(all_articles)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rss_xml, encoding="utf-8")

    print(
        f"✔ Hotovo — {len(all_articles)} článků zapsáno do: "
        f"{out_path.resolve()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
