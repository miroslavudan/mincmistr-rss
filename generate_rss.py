#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generátor RSS feedu pro blog na mincmistr.cz (Shoptet).

Skript stáhne výpis článků z blogu, pro každý článek získá
titulek, URL, datum publikace a perex, a vygeneruje validní
RSS 2.0 XML soubor (feed.xml).

Autor: vygenerováno pro mincmistr.cz
Python 3.8+

Závislosti:
    pip install requests beautifulsoup4 lxml

Použití:
    python3 generate_rss.py
    # volitelně:
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
    # Základní URL e-shopu
    "base_url": "https://www.mincmistr.cz",
    # URL výpisu blogu
    "blog_url": "https://www.mincmistr.cz/blog/",
    # Metadata feedu
    "feed_title": "Mincmistr.cz — Blog",
    "feed_description": (
        "Články o mincích, bankovkách, historii a sběratelství "
        "z blogu Mincmistr.cz."
    ),
    "feed_language": "cs-cz",
    # Kam uložit feed
    "output_path": "feed.xml",
    # Kolik nejnovějších článků zahrnout
    "limit": 20,
    # User-Agent (Shoptet občas blokuje prázdný UA)
    "user_agent": (
        "Mozilla/5.0 (compatible; MincmistrRSSBot/1.0; "
        "+https://www.mincmistr.cz)"
    ),
    # Timeout pro HTTP požadavky (sekundy)
    "request_timeout": 20,
    # Pauza mezi požadavky na detail článku (sekundy) — aby se
    # e-shop nezahltil. 0 = bez pauzy.
    "delay_between_requests": 0.3,
    # Zda stahovat detail článku pro přesnější datum/perex.
    # Pokud výpis obsahuje vše potřebné, můžeš vypnout (rychlejší).
    "fetch_article_detail": True,
}

# Kandidátní CSS selektory pro kartu článku ve výpisu blogu.
# Shoptet má několik šablon, takže zkoušíme postupně.
ARTICLE_CARD_SELECTORS = [
    "article.blog-item",
    "div.blog-item",
    "div.in-blog-list article",
    "div.article-box",
    "div.blog-article",
    "div.blog-post",
    "article",
]

# Selektory pro titulek + odkaz uvnitř karty článku
TITLE_SELECTORS = [
    "h2 a",
    "h3 a",
    "a.blog-item-title",
    ".title a",
    "a[href*='/blog/']",
]

# Selektory pro datum publikace
DATE_SELECTORS = [
    "time[datetime]",
    ".date",
    ".blog-date",
    ".published",
    ".entry-date",
]

# Selektory pro perex (krátký popis)
PEREX_SELECTORS = [
    ".perex",
    ".blog-perex",
    ".description",
    "p.text",
    ".blog-item-text",
    "p",
]

# ============================================================


@dataclass
class Article:
    title: str
    link: str
    pub_date: datetime | None
    description: str

    def to_rss_item(self) -> str:
        """Vygeneruje <item>...</item> blok RSS 2.0."""
        parts = ["    <item>"]
        parts.append(f"      <title>{escape(self.title)}</title>")
        parts.append(f"      <link>{escape(self.link)}</link>")
        parts.append(
            f"      <guid isPermaLink=\"true\">{escape(self.link)}</guid>"
        )
        if self.pub_date is not None:
            # RFC 822 formát je standard pro RSS
            if self.pub_date.tzinfo is None:
                dt = self.pub_date.replace(tzinfo=timezone.utc)
            else:
                dt = self.pub_date
            parts.append(f"      <pubDate>{format_datetime(dt)}</pubDate>")
        if self.description:
            parts.append(
                f"      <description>{escape(self.description)}</description>"
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
    # Shoptet posílá UTF-8, ale apparent_encoding je pojistka
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def select_first(soup, selectors):
    """Vrátí první element, který matchne kterýkoli ze selektorů."""
    for sel in selectors:
        el = soup.select_one(sel)
        if el is not None:
            return el
    return None


def parse_czech_date(text: str) -> datetime | None:
    """Parsuje české formáty data typu '9.4.2026' nebo '9. 4. 2026'."""
    text = text.strip()
    if not text:
        return None
    # Pokus 1: ISO (z atributu datetime="2026-04-09")
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        h = int(m.group(4)) if m.group(4) else 0
        mi = int(m.group(5)) if m.group(5) else 0
        try:
            return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)
        except ValueError:
            pass
    # Pokus 2: D.M.YYYY nebo D. M. YYYY
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d, tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def clean_text(text: str, max_len: int = 500) -> str:
    """Zkrátí a zbaví whitespace."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) > max_len:
        # ořízni na celém slově
        text = text[: max_len].rsplit(" ", 1)[0] + "…"
    return text


def extract_article_cards(soup: BeautifulSoup):
    """Najde seznam karet článků na stránce výpisu."""
    for sel in ARTICLE_CARD_SELECTORS:
        cards = soup.select(sel)
        # Filtrovat jen karty, které obsahují odkaz na /blog/
        cards = [c for c in cards if c.select_one("a[href*='/blog/']")]
        if len(cards) >= 2:
            return cards
    # Fallback: všechny odkazy na /blog/<slug>/ v hlavním obsahu
    links = soup.select("a[href*='/blog/']")
    seen = set()
    pseudo_cards = []
    for a in links:
        href = a.get("href", "")
        if not re.search(r"/blog/[^/]+/?$", href):
            continue
        if href in seen:
            continue
        seen.add(href)
        # použijeme rodiče jako "kartu"
        pseudo_cards.append(a.parent or a)
    return pseudo_cards


def parse_card(card, base_url: str) -> Article | None:
    title_el = select_first(card, TITLE_SELECTORS)
    if title_el is None:
        # někdy je to <a> přímo
        if card.name == "a" and card.get("href"):
            title_el = card
        else:
            return None

    link = title_el.get("href") or ""
    title = clean_text(title_el.get_text() or "", max_len=300)
    if not link or not title:
        return None
    link = urljoin(base_url, link)
    # ignoruj /blog/ kořen a stránkování
    if re.search(r"/blog/?$", link) or "strana-" in link or "?page=" in link:
        return None

    date_el = select_first(card, DATE_SELECTORS)
    pub_date = None
    if date_el is not None:
        dt_attr = date_el.get("datetime") if hasattr(date_el, "get") else None
        if dt_attr:
            pub_date = parse_czech_date(dt_attr)
        if pub_date is None:
            pub_date = parse_czech_date(date_el.get_text())

    perex = ""
    perex_el = select_first(card, PEREX_SELECTORS)
    if perex_el is not None:
        perex = clean_text(perex_el.get_text(), max_len=500)

    return Article(title=title, link=link, pub_date=pub_date, description=perex)


def enrich_from_detail(session: requests.Session, article: Article) -> Article:
    """Stáhne detail článku a doplní chybějící údaje (datum, perex)."""
    try:
        html = fetch(session, article.link)
    except requests.RequestException as e:
        print(f"  ! detail článku nelze stáhnout: {e}", file=sys.stderr)
        return article
    soup = BeautifulSoup(html, "lxml")

    # Datum — zkusíme time[datetime], meta property, viditelný text
    if article.pub_date is None:
        meta = soup.find(
            "meta", attrs={"property": "article:published_time"}
        ) or soup.find("meta", attrs={"name": "date"})
        if meta and meta.get("content"):
            article.pub_date = parse_czech_date(meta["content"])
        if article.pub_date is None:
            time_el = soup.find("time")
            if time_el is not None:
                article.pub_date = parse_czech_date(
                    time_el.get("datetime") or time_el.get_text()
                )
        if article.pub_date is None:
            # hledej datum v běžných kontejnerech
            for sel in [".blog-date", ".date", ".published", ".entry-date"]:
                el = soup.select_one(sel)
                if el:
                    article.pub_date = parse_czech_date(el.get_text())
                    if article.pub_date:
                        break

    # Perex — meta description, úvodní <p>
    if not article.description:
        meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
            "meta", attrs={"property": "og:description"}
        )
        if meta and meta.get("content"):
            article.description = clean_text(meta["content"], max_len=500)
    if not article.description:
        # první smysluplný <p> v hlavním obsahu článku
        main = soup.select_one(
            "article, .blog-detail, .blog-post, .content, main"
        ) or soup
        for p in main.find_all("p"):
            text = clean_text(p.get_text(), max_len=500)
            if len(text) > 40:
                article.description = text
                break

    return article


def build_rss(articles: list[Article]) -> str:
    now = format_datetime(datetime.now(tz=timezone.utc))
    items_xml = "\n".join(a.to_rss_item() for a in articles)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
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
    parser.add_argument(
        "--output", "-o", default=CONFIG["output_path"],
        help=f"Cesta k výstupnímu souboru (default: {CONFIG['output_path']})",
    )
    parser.add_argument(
        "--limit", "-n", type=int, default=CONFIG["limit"],
        help=f"Počet nejnovějších článků (default: {CONFIG['limit']})",
    )
    parser.add_argument(
        "--no-detail", action="store_true",
        help="Nestahovat detail každého článku (rychlejší, méně přesné)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Podrobnější výpis",
    )
    args = parser.parse_args()

    session = make_session()

    print(f"▶ Stahuji výpis blogu: {CONFIG['blog_url']}")
    try:
        html = fetch(session, CONFIG["blog_url"])
    except requests.RequestException as e:
        print(f"❌ Nepodařilo se stáhnout výpis blogu: {e}", file=sys.stderr)
        return 1

    soup = BeautifulSoup(html, "lxml")
    cards = extract_article_cards(soup)
    if not cards:
        print(
            "❌ Na stránce jsem nenašel žádné karty článků. "
            "Zkontroluj selektory v sekci ARTICLE_CARD_SELECTORS.",
            file=sys.stderr,
        )
        return 2

    print(f"  nalezeno {len(cards)} potenciálních článků")

    articles: list[Article] = []
    seen_links: set[str] = set()
    for card in cards:
        art = parse_card(card, CONFIG["base_url"])
        if art is None:
            continue
        if art.link in seen_links:
            continue
        seen_links.add(art.link)
        articles.append(art)
        if len(articles) >= args.limit:
            break

    if not articles:
        print("❌ Žádné články se nepodařilo naparsovat.", file=sys.stderr)
        return 3

    # Obohatit detaily, pokud je to žádoucí
    if CONFIG["fetch_article_detail"] and not args.no_detail:
        print(f"▶ Stahuji detaily {len(articles)} článků…")
        for i, art in enumerate(articles, 1):
            if args.verbose:
                print(f"  [{i}/{len(articles)}] {art.link}")
            articles[i - 1] = enrich_from_detail(session, art)
            if CONFIG["delay_between_requests"] > 0:
                time.sleep(CONFIG["delay_between_requests"])

    # Seřaď od nejnovějšího (ty bez data jdou na konec)
    articles.sort(
        key=lambda a: a.pub_date or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    rss_xml = build_rss(articles)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rss_xml, encoding="utf-8")

    print(f"✔ Hotovo — {len(articles)} článků zapsáno do: {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
