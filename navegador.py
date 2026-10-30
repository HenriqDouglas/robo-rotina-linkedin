"""Chrome próprio do robô: um perfil separado, com o LinkedIn da pessoa, aberto só para LER páginas.

Usado quando o config tem "navegador": "proprio" (por exemplo, um segundo robô no mesmo PC, em que o
Chrome de todo dia está logado em outra conta). Abre o Chrome instalado (não um navegador oculto),
minimizado, devagar, e nunca clica nem digita em nada.
"""
from __future__ import annotations

import random
import time
from pathlib import Path

BLOQUEIO = ("/login", "/uas/", "authwall", "/checkpoint")
LINKS_JS = "els => els.map(e => [e.href.split('?')[0], (e.innerText || '').trim().slice(0, 100)])"


class LoginNecessario(RuntimeError):
    pass


def _abrir(p, pasta: Path, minimizado: bool = True):
    return p.chromium.launch_persistent_context(
        str(pasta), channel="chrome", headless=False, no_viewport=True,
        args=["--start-minimized"] if minimizado else [])


def ler_paginas(pasta: Path, paginas: list[dict], log=print) -> list[dict]:
    """paginas: [{"url": ..., ...}]. Devolve cada uma com o texto e os links de perfil encontrados."""
    from playwright.sync_api import sync_playwright
    lidas = []
    with sync_playwright() as p:
        ctx = _abrir(p, pasta)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            for item in paginas:
                page.goto(item["url"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(random.randint(4000, 8000))  # ritmo de quem está lendo
                if any(b in page.url for b in BLOQUEIO):
                    raise LoginNecessario(page.url)
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(random.randint(1500, 3000))
                texto = page.inner_text("main") if page.locator("main").count() else page.inner_text("body")
                links, vistos = [], set()
                for href, rotulo in page.eval_on_selector_all("a[href*='/in/']", LINKS_JS):
                    if href not in vistos:
                        vistos.add(href)
                        links.append({"url": href, "texto": rotulo})
                lidas.append({**item, "texto": texto[:15000], "links_de_perfil": links[:60]})
                log(f"navegador: lida {item['url'][:90]}")
        finally:
            ctx.close()
    return lidas


def logado(pasta: Path) -> bool:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _abrir(p, pasta)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            return not any(b in page.url for b in BLOQUEIO)
        finally:
            ctx.close()


def entrar(pasta: Path, espera_s: int = 900) -> bool:
    """Abre o Chrome do robô na tela de login e espera a pessoa entrar (senha e código, se pedir)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _abrir(p, pasta, minimizado=False)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=60000)
            fim = time.time() + espera_s
            while time.time() < fim:
                if "/feed" in page.url:
                    page.wait_for_timeout(2000)
                    return True
                page.wait_for_timeout(2000)
            return False
        finally:
            ctx.close()
