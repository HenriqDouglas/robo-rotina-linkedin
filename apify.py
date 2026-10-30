"""Busca de posts no Apify.

Segue o padrão de lib/apify_client.py do sergebulaev/linkedin-skills (MIT):
token no header Authorization (nunca na URL), endpoint run-sync-get-dataset-items
e retry com backoff em 408/429/5xx.
"""
from __future__ import annotations

import random
import time
from datetime import datetime, timezone

import requests

BASE = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
RETRY = {408, 429, 500, 502, 503, 504}


def run_actor(token: str, actor: str, payload: dict, timeout: float = 300) -> list[dict]:
    for tentativa in range(3):
        try:
            r = requests.post(
                BASE.format(actor=actor),
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=timeout,
            )
        except (requests.ConnectionError, requests.Timeout):
            if tentativa == 2:
                raise
        else:
            if r.status_code < 400:
                dados = r.json()
                if isinstance(dados, dict) and "error" in dados:
                    raise RuntimeError(f"Apify {actor}: {dados['error']}")
                return dados if isinstance(dados, list) else []
            if r.status_code not in RETRY or tentativa == 2:
                raise RuntimeError(f"Apify {actor}: HTTP {r.status_code} {r.text[:300]}")
        time.sleep(0.6 * 2 ** tentativa + random.uniform(0, 0.25))
    return []


def _pick(d: dict, *caminhos):
    """Primeiro valor não vazio entre vários caminhos ('a.b.c'). O formato de saída do ator não é documentado."""
    for caminho in caminhos:
        v = d
        for parte in caminho.split("."):
            v = v.get(parte) if isinstance(v, dict) else None
        if v not in (None, "", [], {}):
            return v
    return None


def _data(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def normalizar(item: dict, keyword: str) -> dict | None:
    url = _pick(item, "post_url", "postUrl", "url", "share_url", "link")
    texto = _pick(item, "text", "content", "commentary", "post_text")
    if not url or not texto:
        return None
    urn = _pick(item, "activity_id", "activity_urn", "urn", "full_urn", "postId", "id") or url
    data = _data(_pick(item, "posted_at.timestamp", "posted_at.date", "postedAt", "date", "posted_at"))
    return {
        "id": str(urn).split(":")[-1],
        "url": url.split("?")[0],
        "autor": _pick(item, "author.name", "author.full_name", "authorName", "author_name")
        or " ".join(filter(None, [_pick(item, "author.first_name"), _pick(item, "author.last_name")])),
        "autor_url": _pick(item, "author.profile_url", "author.url", "authorUrl", "author_profile_url"),
        "headline": _pick(item, "author.headline", "author.occupation", "authorHeadline", "author_headline") or "",
        "texto": str(texto),
        "data_post": data.isoformat() if data else None,
        "reacoes": _pick(item, "stats.total_reactions", "reactionsCount", "num_reactions", "likes") or 0,
        "comentarios": _pick(item, "stats.comments", "commentsCount", "num_comments", "comments_count") or 0,
        "keyword": keyword,
    }
