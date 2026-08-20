"""
SEO routes: robots.txt and XML sitemaps.
"""

from __future__ import annotations

import html
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.db.session import get_db
from src.models.bottle import Bottle

router = APIRouter()

SITEMAP_BOTTLES_PER_FILE = 10_000

STATIC_PAGES: tuple[tuple[str, str, str], ...] = (
    ("/", "daily", "1.0"),
    ("/bottles", "daily", "0.9"),
    ("/trending", "daily", "0.8"),
    ("/brands", "weekly", "0.8"),
    ("/market", "daily", "0.8"),
    ("/about", "monthly", "0.5"),
    ("/terms", "yearly", "0.3"),
    ("/privacy", "yearly", "0.3"),
)


def _site_url() -> str:
    return get_settings().public_site_url.rstrip("/")


def _format_lastmod(value: datetime | None) -> str | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _render_url(loc: str, lastmod: str | None = None, changefreq: str | None = None, priority: str | None = None) -> str:
    parts = [f"  <url><loc>{html.escape(loc)}</loc>"]
    if lastmod:
        parts.append(f"<lastmod>{lastmod}</lastmod>")
    if changefreq:
        parts.append(f"<changefreq>{changefreq}</changefreq>")
    if priority:
        parts.append(f"<priority>{priority}</priority>")
    parts.append("</url>")
    return "".join(parts)


def _xml_response(body: str) -> Response:
    content = f'<?xml version="1.0" encoding="UTF-8"?>\n{body}'
    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _bottle_filter():
    return (Bottle.is_active.is_(True)) & (Bottle.price_count > 0)


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> PlainTextResponse:
    base = _site_url()
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /api/",
        "Disallow: /auth/",
        "Disallow: /profile",
        "Disallow: /collections",
        "Disallow: /alerts",
        "Disallow: /admin/",
        "Disallow: /search?",
        "",
        f"Sitemap: {base}/sitemap.xml",
    ]
    return PlainTextResponse("\n".join(lines) + "\n")


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_index(db: AsyncSession = Depends(get_db)) -> Response:
    base = _site_url()
    total_bottles = await db.scalar(
        select(func.count()).select_from(Bottle).where(_bottle_filter())
    ) or 0
    bottle_files = max(1, math.ceil(total_bottles / SITEMAP_BOTTLES_PER_FILE)) if total_bottles else 0

    entries = [f"  <sitemap><loc>{html.escape(base)}/sitemap-static.xml</loc></sitemap>"]
    for page in range(1, bottle_files + 1):
        entries.append(
            f"  <sitemap><loc>{html.escape(base)}/sitemap-bottles-{page}.xml</loc></sitemap>"
        )

    body = (
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</sitemapindex>"
    )
    return _xml_response(body)


@router.get("/sitemap-static.xml", include_in_schema=False)
async def sitemap_static() -> Response:
    base = _site_url()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [
        _render_url(f"{base}{path}", lastmod=today, changefreq=freq, priority=priority)
        for path, freq, priority in STATIC_PAGES
    ]
    body = (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )
    return _xml_response(body)


@router.get("/sitemap-bottles-{page}.xml", include_in_schema=False)
async def sitemap_bottles(page: int, db: AsyncSession = Depends(get_db)) -> Response:
    if page < 1:
        raise HTTPException(status_code=404, detail="Sitemap not found")

    total_bottles = await db.scalar(
        select(func.count()).select_from(Bottle).where(_bottle_filter())
    ) or 0
    if total_bottles == 0:
        raise HTTPException(status_code=404, detail="Sitemap not found")

    max_page = math.ceil(total_bottles / SITEMAP_BOTTLES_PER_FILE)
    if page > max_page:
        raise HTTPException(status_code=404, detail="Sitemap not found")

    offset = (page - 1) * SITEMAP_BOTTLES_PER_FILE
    result = await db.execute(
        select(Bottle.id, Bottle.last_price_date, Bottle.updated_at)
        .where(_bottle_filter())
        .order_by(Bottle.id)
        .offset(offset)
        .limit(SITEMAP_BOTTLES_PER_FILE)
    )
    rows = result.all()
    if not rows:
        raise HTTPException(status_code=404, detail="Sitemap not found")

    base = _site_url()
    urls = []
    for bottle_id, last_price_date, updated_at in rows:
        lastmod = _format_lastmod(last_price_date or updated_at)
        urls.append(
            _render_url(
                f"{base}/bottles/{bottle_id}",
                lastmod=lastmod,
                changefreq="weekly",
                priority="0.6",
            )
        )

    body = (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )
    return _xml_response(body)
