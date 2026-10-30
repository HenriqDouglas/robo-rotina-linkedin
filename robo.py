"""Robô da rotina diária do LinkedIn → Telegram.

Só sugere: curtir, comentar, conectar, responder e publicar são feitos à mão.

Uso: python robo.py <momento> [--dry-run]
Instalação: vincular, definir, checar, configurar
Rotina: coleta, curtir_comentar, conectar, responder, publicar, resumo
Atualização: atualizar, versao
Outros: teste, pronto, status, escutar, config
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import apify
import atualizar
from telegram import Telegram, esc

BASE = Path(__file__).resolve().parent
LOGS = BASE / "logs"
DADOS = BASE / "dados"

# IDs de país usados no filtro de localização da busca de pessoas do LinkedIn (geoUrn)
GEO = {
    "US": "103644278", "BR": "106057199", "CA": "101174742", "GB": "101165590", "IE": "104738515",
    "PT": "100364837", "ES": "105646813", "DE": "101282230", "NL": "102890719", "FR": "105015875",
    "IT": "103350119", "CH": "106693272", "AU": "101452733", "MX": "103323778", "AR": "100446943",
}


# ---------- infraestrutura ----------

def log(msg: str):
    linha = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(linha)
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / f"robo-{date.today():%Y-%m}.log", "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def carregar_env() -> dict:
    env = {}
    arq = BASE / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8-sig").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return {**env, **{k: os.environ[k] for k in env if k in os.environ}}


def gravar_env(chave: str, valor):
    arq = BASE / ".env"
    linhas = arq.read_text(encoding="utf-8-sig").splitlines() if arq.exists() else []
    linhas = [l for l in linhas if not l.strip().startswith(chave + "=")] + [f"{chave}={valor}"]
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def ler(caminho: str) -> str:
    return (BASE / caminho).read_text(encoding="utf-8-sig")


def _juntar(base: dict, local: dict) -> dict:
    out = dict(base)
    for k, v in local.items():
        out[k] = _juntar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def carregar_config() -> dict:
    """config.json traz os padrões (vem nas atualizações); dados/config-local.json, os ajustes da pessoa."""
    cfg = json.loads(ler("config.json"))
    local = DADOS / "config-local.json"
    return _juntar(cfg, json.loads(local.read_text(encoding="utf-8-sig"))) if local.exists() else cfg


def carregar_perfil() -> dict | None:
    arq = DADOS / "perfil.json"
    return json.loads(arq.read_text(encoding="utf-8-sig")) if arq.exists() else None


def montar_prompt(arquivo: str, perfil: dict | None = None, **extra) -> str:
    """Preenche os placeholders: perfil e arquivos de referência primeiro, dados de terceiros por último."""
    p = perfil or {}
    texto = ler(arquivo)
    campos = {
        "NOME": p.get("nome", ""), "PRIMEIRO_NOME": p.get("primeiro_nome", ""),
        "OBJETIVO": p.get("objetivo", ""), "CARGOS": ", ".join(p.get("cargos_alvo", [])),
        "AREA": p.get("area", ""), "PAISES": ", ".join(p.get("paises_alvo", [])), "PUBLICO": p.get("publico", ""),
        "PILARES": "; ".join(p.get("pilares", [])), "IDIOMA": p.get("idioma", "English"),
        "FUSO": p.get("cidade_fuso", ""),
    }
    for k, v in campos.items():
        texto = texto.replace("{" + k + "}", str(v))
    arquivos = {"VOICE": "dados/voice-profile.md", "STORY": "dados/story-bank.md",
                "TEMPLATES": "prompts/ref/comment-templates.md", "VOICE_RULES": "prompts/ref/voice-rules.md",
                "HUMANIZER": "prompts/ref/humanizer-checklist.md", "HOOKS": "prompts/ref/hook-formulas.md"}
    for k, caminho in arquivos.items():
        if "{" + k + "}" in texto:
            texto = texto.replace("{" + k + "}", ler(caminho))
    for k, v in extra.items():
        texto = texto.replace("{" + k + "}", str(v))
    return texto


def abrir_db() -> sqlite3.Connection:
    db = sqlite3.connect(BASE / "estado.sqlite", timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY, url TEXT, autor TEXT, autor_url TEXT, headline TEXT, texto TEXT,
            data_post TEXT, reacoes INTEGER, comentarios INTEGER, keyword TEXT,
            coletado_em TEXT, status TEXT DEFAULT 'novo');
        CREATE TABLE IF NOT EXISTS pessoas (
            url TEXT PRIMARY KEY, nome TEXT, cargo TEXT, grupo TEXT, sugerido_em TEXT);
        CREATE TABLE IF NOT EXISTS tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT, qtd INTEGER, ref TEXT, criado_em TEXT,
            status TEXT DEFAULT 'pendente', msg_id INTEGER);
        CREATE TABLE IF NOT EXISTS publicacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tema TEXT, texto TEXT, criado_em TEXT);
        CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
        """
    )
    return db


def kv_get(db, k, padrao=None):
    row = db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return row["v"] if row else padrao


def kv_set(db, k, v):
    db.execute("INSERT INTO kv(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))
    db.commit()


def claude(prompt: str, schema: dict, cfg: dict, extra: list[str] | None = None) -> dict:
    """Chama `claude -p` com saída JSON validada por schema. Sem ferramentas, a menos que `extra` libere."""
    exe = shutil.which("claude") or str(Path.home() / ".local/bin/claude.exe")
    args = [exe, "-p", "--output-format", "json", "--json-schema", json.dumps(schema),
            "--model", cfg["claude"]["modelo"]]
    args += extra if extra is not None else ["--tools", "", "--strict-mcp-config"]
    r = subprocess.run(args, input=prompt, capture_output=True, text=True, encoding="utf-8",
                       timeout=cfg["claude"]["timeout_s"], cwd=BASE,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))  # sem janela sob pythonw
    try:
        saida = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude -p sem JSON (código {r.returncode}): {r.stdout[:300]} {r.stderr[:300]}")
    if saida.get("is_error") or not saida.get("structured_output"):
        raise RuntimeError(f"claude -p falhou: {saida.get('subtype')} {str(saida.get('result'))[:300]}")
    log(f"claude -p ok (custo de referência US$ {saida.get('total_cost_usd', 0):.3f})")
    return saida["structured_output"]


FERRAMENTAS_CHROME = ",".join(f"mcp__claude-in-chrome__{t}" for t in
                              ("tabs_context_mcp", "tabs_create_mcp", "tabs_close_mcp", "navigate",
                               "read_page", "find", "get_page_text"))
CHROME = ["--chrome", "--tools", "", "--allowedTools", FERRAMENTAS_CHROME]


def pausar(tg: Telegram, motivo: str):
    (BASE / "PAUSADO").write_text(motivo, encoding="utf-8")
    log(f"pausado: {motivo}")
    tg.enviar("⏸ <b>Robô pausado</b>: " + esc(motivo) +
              "\nConfira o LinkedIn no navegador. Para religar, mande /religar aqui.")


def botoes(tarefa_id: int):
    return [[("✅ Feito", f"f:{tarefa_id}"), ("⏭ Pular", f"p:{tarefa_id}")]]


def nova_tarefa(db, tipo: str, qtd: int, ref: str = "") -> int:
    cur = db.execute("INSERT INTO tarefas(tipo, qtd, ref, criado_em) VALUES(?,?,?,?)",
                     (tipo, qtd, ref, datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return cur.lastrowid


def enviar_tarefa(tg: Telegram, db, tipo: str, qtd: int, texto: str, ref: str = ""):
    if tg.dry_run:  # no teste não registra tarefa
        tg.enviar(texto, botoes(0))
        return
    tid = nova_tarefa(db, tipo, qtd, ref)
    msg_id = tg.enviar(texto, botoes(tid))
    db.execute("UPDATE tarefas SET msg_id=? WHERE id=?", (msg_id, tid))
    db.commit()


def ouvinte_ativo(db) -> bool:
    batida = kv_get(db, "ouvinte_batida")
    return bool(batida) and datetime.now() - datetime.fromisoformat(batida) < timedelta(minutes=2)


def tratar_callback(tg: Telegram, db, cb: dict):
    acao, _, tid = cb.get("data", "").partition(":")
    if acao == "u":  # botão ⬆️ Atualizar
        try:
            tg.responder_callback(cb["id"], "Atualizando…")
            tg.marcar_mensagem(cb["message"]["message_id"], "⏳ Atualizando")
        except RuntimeError as e:
            log(f"aviso Telegram: {e}")
        atualizar_agora(tg, db, carregar_config())
        return
    if acao in ("f", "p") and tid.isdigit():
        status = "feito" if acao == "f" else "pulado"
        db.execute("UPDATE tarefas SET status=? WHERE id=?", (status, int(tid)))
        db.commit()
    # o clique pode ter horas (o robô não fica ligado); o Telegram recusa confirmar clique velho
    for passo in (lambda: tg.responder_callback(cb["id"], "Registrado"),
                  lambda: tg.marcar_mensagem(cb["message"]["message_id"], "✅ Feito" if acao == "f" else "⏭ Pulado")):
        try:
            passo()
        except RuntimeError as e:
            log(f"aviso Telegram: {e}")


def processar_updates(tg: Telegram, db, espera: int = 0) -> list[str]:
    """Lê cliques em Feito/Pular e devolve os textos recebidos do chat configurado.
    Com o ouvinte ligado, só ele lê (duas leituras simultâneas dão conflito)."""
    if tg.dry_run or not tg.chat_id or (espera == 0 and ouvinte_ativo(db)):
        return []
    offset = kv_get(db, "tg_offset")
    textos = []
    for up in tg.updates(int(offset) if offset else None, espera):
        kv_set(db, "tg_offset", up["update_id"] + 1)
        cb = up.get("callback_query")
        msg = up.get("message") or {}
        if cb and str(cb["message"]["chat"]["id"]) == tg.chat_id:  # só aceita o chat configurado
            tratar_callback(tg, db, cb)
        elif msg.get("text") and str(msg["chat"]["id"]) == tg.chat_id:
            textos.append(msg["text"].strip())
    return textos


def descartar_pendentes(tg: Telegram, db):
    """Pula mensagens antigas para que não sejam lidas como resposta."""
    if tg.dry_run:
        return
    ups = tg.updates(None, 0)
    if ups:
        kv_set(db, "tg_offset", ups[-1]["update_id"] + 1)
        tg.updates(ups[-1]["update_id"] + 1, 0)


class Conversa:
    """Pergunta e espera a resposta em texto: no Telegram ou, no --dry-run, no terminal."""

    def __init__(self, tg: Telegram, db):
        self.tg, self.db = tg, db

    def dizer(self, texto: str, html_mode: bool = True):
        self.tg.enviar(texto, html_mode=html_mode)

    def perguntar(self, texto: str) -> str:
        self.dizer(texto)
        if self.tg.dry_run:
            return input("> ").strip()
        while True:  # a batida avisa os momentos agendados para não lerem o Telegram junto
            kv_set(self.db, "ouvinte_batida", datetime.now().isoformat(timespec="seconds"))
            textos = processar_updates(self.tg, self.db, espera=50)
            if textos:
                return textos[-1]


def trava(cfg):
    """Porta local como trava: só um processo lê o Telegram por vez (o Telegram recusa duas leituras)."""
    import socket
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", cfg.get("porta_trava", 47831)))
    except OSError:
        return None
    return s


# ---------- instalação ----------

def vincular(env, db):
    """Grava no .env o chat de quem mandar a primeira mensagem para o bot."""
    if not env.get("TELEGRAM_BOT_TOKEN"):
        raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado no .env")
    tg = Telegram(env["TELEGRAM_BOT_TOKEN"], None)
    print("Abra o Telegram, entre no seu bot e mande 'oi'. Esperando até 5 minutos...")
    fim, offset = time.time() + 300, None
    while time.time() < fim:
        for u in tg.updates(offset, 30):
            offset = u["update_id"] + 1
            chat = (u.get("message") or {}).get("chat") or {}
            if chat.get("type") == "private":
                gravar_env("TELEGRAM_CHAT_ID", chat["id"])
                tg.updates(offset, 0)
                kv_set(db, "tg_offset", offset)
                tg.chat_id = str(chat["id"])
                tg.enviar("✅ <b>Robô da rotina LinkedIn</b> conectado a este chat.")
                print(f"Pronto: chat {chat['id']} ({chat.get('first_name', '')}) gravado.")
                return
    print("Nenhuma mensagem chegou. Confira se mandou 'oi' para o bot certo e rode de novo.")
    sys.exit(1)


def checar(alvo: str, cfg, env, tg):
    """Testes da instalação: claude, chrome, apify ou telegram."""
    if alvo == "claude":
        claude("Reply with ok=true.", {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}, cfg)
    elif alvo == "chrome":
        res = claude("Call tabs_context_mcp once (create a tab if it asks you to). Do not open any page. "
                     "Return ok=true if the browser answered, and in `detalhe` what happened.",
                     {"type": "object", "properties": {"ok": {"type": "boolean"}, "detalhe": {"type": "string"}},
                      "required": ["ok", "detalhe"]}, cfg, extra=CHROME)
        if not res["ok"]:
            raise RuntimeError("Chrome não respondeu: " + res["detalhe"])
    elif alvo == "apify":
        if not env.get("APIFY_TOKEN"):
            raise RuntimeError("APIFY_TOKEN não configurado no .env")
        itens = apify.run_actor(env["APIFY_TOKEN"], cfg["coleta"]["actor"],
                                {"keyword": '"hiring"', "sort_type": "relevance", "date_filter": "past-24h",
                                 "total_posts": 2, "limit": 2})
        print(f"Apify devolveu {len(itens)} posts")
    elif alvo == "telegram":
        tg.enviar("✅ <b>Robô da rotina LinkedIn</b>: teste de mensagem.", botoes(0))
    else:
        raise RuntimeError("use: checar claude|chrome|apify|telegram")
    print(f"OK: {alvo}")


SCHEMA_LEITURA = {
    "type": "object",
    "properties": {
        "nome": {"type": "string"}, "primeiro_nome": {"type": "string"}, "headline": {"type": "string"},
        "localizacao": {"type": "string"}, "sobre": {"type": "string"},
        "experiencias": {"type": "array", "items": {"type": "object", "properties": {
            "cargo": {"type": "string"}, "empresa": {"type": "string"}, "periodo": {"type": "string"},
            "descricao": {"type": "string"}}, "required": ["cargo", "empresa", "periodo", "descricao"]}},
        "formacao": {"type": "array", "items": {"type": "string"}},
        "certificacoes": {"type": "array", "items": {"type": "string"}},
        "skills": {"type": "array", "items": {"type": "string"}},
        "idiomas": {"type": "array", "items": {"type": "string"}},
        "fatos_com_numeros": {"type": "array", "items": {"type": "string"}},
        "lacunas": {"type": "array", "items": {"type": "string"}},
        "bloqueado": {"type": "boolean"}, "alerta": {"type": "string"},
    },
    "required": ["nome", "primeiro_nome", "headline", "experiencias", "fatos_com_numeros", "lacunas", "bloqueado"],
}

SCHEMA_GERAR = {
    "type": "object",
    "properties": {
        "perfil": {"type": "object", "properties": {
            "nome": {"type": "string"}, "primeiro_nome": {"type": "string"}, "idioma": {"type": "string"},
            "cidade_fuso": {"type": "string"}, "objetivo": {"type": "string"},
            "cargos_alvo": {"type": "array", "items": {"type": "string"}},
            "paises_alvo": {"type": "array", "items": {"type": "string"}}, "remoto": {"type": "boolean"},
            "area": {"type": "string"}, "publico": {"type": "string"},
            "pilares": {"type": "array", "items": {"type": "string"}},
            "linha_base": {"type": "string"}},
            "required": ["nome", "primeiro_nome", "idioma", "cidade_fuso", "objetivo", "cargos_alvo", "paises_alvo",
                         "remoto", "area", "publico", "pilares", "linha_base"]},
        "voice_profile_md": {"type": "string"},
        "story_bank_md": {"type": "string"},
        "mensagens": {"type": "object", "properties": {"geral": {"type": "string"}, "recrutador": {"type": "string"}},
                      "required": ["geral", "recrutador"]},
        "coleta_keywords": {"type": "array", "items": {"type": "string"}},
        "grupos": {"type": "array", "items": {"type": "object", "properties": {
            "nome": {"type": "string", "enum": ["recrutadores", "area"]}, "rotulo_pt": {"type": "string"},
            "keywords": {"type": "string"}, "descricao": {"type": "string"}},
            "required": ["nome", "rotulo_pt", "keywords", "descricao"]}},
        "resumo_pt": {"type": "string"},
    },
    "required": ["perfil", "voice_profile_md", "story_bank_md", "mensagens", "coleta_keywords", "grupos", "resumo_pt"],
}

PERGUNTAS_FIXAS = [
    "Quais cargos você quer conquistar? Liste de 2 a 4 (ex.: Product Manager, Data Analyst).",
    "Em quais países você quer trabalhar e em que formato? (ex.: EUA e Canadá, remoto; ou Portugal, híbrido)",
    "Em que idioma você quer comentar e publicar no LinkedIn? (ex.: inglês, português)",
    "Em que cidade você mora? Serve para sugerir o melhor horário de publicar.",
    "Conte de 3 a 5 resultados reais do seu trabalho, com números: o que você fez, o que mudou, quanto e em "
    "quanto tempo. Só fatos que você defenderia numa entrevista. O robô nunca vai inventar números.",
    "Como você NÃO quer soar nos comentários e posts? E como quer soar? (ex.: não quero parecer que estou me "
    "vendendo; quero soar leve, como quem troca ideias)",
    "No LinkedIn, abra seu perfil e veja o painel de Analytics: visualizações do perfil, aparições em buscas, "
    "impressões e número de conexões. Mande os números (ou responda 'pular').",
]

OK = {"ok", "sim", "aprovar", "aprovado", "pode", "pode salvar", "salvar"}


def configurar(cfg, db, env, tg, dry=False):
    """Onboarding: lê o perfil da pessoa, faz perguntas e gera voz, histórias, palavras-chave e grupos."""
    conv = Conversa(tg, db)
    descartar_pendentes(tg, db)
    conv.dizer("👋 <b>Vamos configurar o seu robô da rotina LinkedIn.</b>\n"
               "Vou ler o seu perfil (só ler, sem clicar em nada) e depois fazer algumas perguntas. "
               "Responda aqui mesmo, com calma.")
    while True:
        resposta = conv.perguntar("🔗 Mande o link do seu perfil do LinkedIn (ex.: https://www.linkedin.com/in/seu-nome/)")
        m = re.search(r"linkedin\.com/in/([^/?#\s]+)", resposta)
        if m:
            break
        conv.dizer("Não reconheci o link. Ele tem o formato linkedin.com/in/seu-nome.")
    url = f"https://www.linkedin.com/in/{m.group(1)}/"
    conv.dizer("🔎 Lendo o seu perfil no Chrome. Leva alguns minutos, pode deixar o Chrome aberto.")
    lido = claude(montar_prompt("prompts/ler_perfil.md", PERFIL_URL=url), SCHEMA_LEITURA, cfg, extra=CHROME)
    if lido["bloqueado"]:
        raise RuntimeError("o LinkedIn bloqueou a leitura do perfil: " + lido.get("alerta", ""))
    DADOS.mkdir(exist_ok=True)
    (DADOS / "perfil-lido.json").write_text(json.dumps({"url": url, **lido}, ensure_ascii=False, indent=2), encoding="utf-8")
    conv.dizer(f"✅ Li o perfil de <b>{esc(lido['nome'])}</b>: {esc(lido['headline'])}\n"
               f"{len(lido['experiencias'])} experiências, {len(lido.get('skills', []))} competências.\n\n"
               "Agora as perguntas.")

    perguntas = PERGUNTAS_FIXAS + lido["lacunas"][:5]
    respostas = []
    for i, p in enumerate(perguntas, 1):
        r = conv.perguntar(f"<b>Pergunta {i}/{len(perguntas)}</b>\n{esc(p)}")
        respostas.append({"pergunta": p, "resposta": r})

    ajustes: list[str] = []
    while True:
        conv.dizer("✍️ Montando o seu perfil de voz, as suas histórias e as buscas. Mais alguns minutos.")
        g = claude(montar_prompt("prompts/gerar_perfil.md",
                                 N_COMENTAR=cfg["metas"]["comentar_por_dia"],
                                 PERFIL_LIDO=json.dumps(lido, ensure_ascii=False, indent=1),
                                 RESPOSTAS=json.dumps(respostas, ensure_ascii=False, indent=1),
                                 AJUSTES="\n".join(f"- {a}" for a in ajustes) or "(none)"),
                   SCHEMA_GERAR, cfg)
        sem_geo = [c for c in g["perfil"]["paises_alvo"] if c.upper() not in GEO]
        grupos = "\n".join(f"• {esc(x['rotulo_pt'])}: <code>{esc(x['keywords'])}</code>" for x in g["grupos"])
        conv.dizer("📚 <b>Suas histórias</b> (o robô só usa números daqui):")
        conv.dizer(g["story_bank_md"], html_mode=False)
        conv.dizer(f"🧭 <b>Resumo</b>\n{esc(g['resumo_pt'])}\n\n"
                   f"🎯 Cargos: {esc(', '.join(g['perfil']['cargos_alvo']))}\n"
                   f"🌎 Países: {esc(', '.join(g['perfil']['paises_alvo']))}"
                   + (" · remoto" if g["perfil"]["remoto"] else "") + "\n"
                   f"🗣 Idioma: {esc(g['perfil']['idioma'])}\n"
                   f"🔎 Posts sobre: {esc(' · '.join(g['coleta_keywords']))}\n"
                   f"🤝 Pessoas:\n{grupos}"
                   + (f"\n⚠️ Sem filtro de país para: {esc(', '.join(sem_geo))}" if sem_geo else ""))
        r = conv.perguntar("Responda <b>OK</b> para salvar e ligar o robô, ou escreva o que quer mudar "
                           "(ex.: \"tire a história X\", \"quero focar em fintechs\").")
        if r.strip().lower().rstrip("!.") in OK:
            break
        ajustes.append(r)

    salvar_configuracao(g, cfg, db, dry)
    conv.dizer("🎉 <b>Configuração salva.</b> A partir do próximo dia útil você recebe aqui o que fazer.\n"
               + COMANDOS)


def salvar_configuracao(g: dict, cfg: dict, db, dry: bool):
    perfil = {**g["perfil"], "configurado_em": date.today().isoformat()}
    if dry:  # no teste só o Telegram é simulado: os arquivos são gravados
        print(json.dumps(g["mensagens"], ensure_ascii=False, indent=2))
    DADOS.mkdir(exist_ok=True)
    (DADOS / "perfil.json").write_text(json.dumps(perfil, ensure_ascii=False, indent=2), encoding="utf-8")
    (DADOS / "voice-profile.md").write_text(g["voice_profile_md"], encoding="utf-8")
    (DADOS / "story-bank.md").write_text(g["story_bank_md"], encoding="utf-8")
    (DADOS / "mensagens.json").write_text(json.dumps(g["mensagens"], ensure_ascii=False, indent=2), encoding="utf-8")
    geo = [GEO[c.upper()] for c in g["perfil"]["paises_alvo"] if c.upper() in GEO]
    qtd = {"recrutadores": cfg["metas"]["conectar_recrutadores"], "area": cfg["metas"]["conectar_area"]}
    arq = DADOS / "config-local.json"  # fica fora do código: as atualizações não apagam
    local = json.loads(arq.read_text(encoding="utf-8-sig")) if arq.exists() else {}
    local.setdefault("coleta", {})["keywords"] = g["coleta_keywords"]
    local.setdefault("pessoas", {})["grupos"] = [
        {"nome": x["nome"], "rotulo": x["rotulo_pt"], "qtd": qtd[x["nome"]],
         "keywords": x["keywords"], "descricao": x["descricao"], "geo_urns": geo} for x in g["grupos"]]
    arq.write_text(json.dumps(local, ensure_ascii=False, indent=2), encoding="utf-8")
    db.execute("DELETE FROM kv WHERE k LIKE 'pagina_%'")
    db.commit()
    log("configurar: perfil salvo")


# ---------- momentos ----------

def coleta(cfg, db, env, dry=False) -> int:
    c = cfg["coleta"]
    token = env.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN não configurado no .env")
    limite = datetime.now(timezone.utc) - timedelta(hours=c["max_idade_horas"])
    novos = 0
    for kw in c["keywords"]:
        payload = {"keyword": kw, "sort_type": c["sort_type"], "date_filter": c["date_filter"],
                   "total_posts": c["posts_por_keyword"], "limit": c["posts_por_keyword"]}
        itens = apify.run_actor(token, c["actor"], payload)
        if itens:
            (LOGS / "amostra_apify.json").write_text(json.dumps(itens[:2], ensure_ascii=False, indent=2), encoding="utf-8")
        for item in itens:
            p = apify.normalizar(item, kw)
            if not p or len(p["texto"]) < c["min_caracteres"]:
                continue
            if p["data_post"] and datetime.fromisoformat(p["data_post"]) < limite:
                continue
            cur = db.execute(
                "INSERT OR IGNORE INTO posts(id,url,autor,autor_url,headline,texto,data_post,reacoes,comentarios,keyword,coletado_em)"
                " VALUES(:id,:url,:autor,:autor_url,:headline,:texto,:data_post,:reacoes,:comentarios,:keyword,:agora)",
                {**p, "agora": datetime.now().isoformat(timespec="seconds")})
            novos += cur.rowcount
        log(f"coleta '{kw}': {len(itens)} itens")
    db.commit()
    kv_set(db, "ultima_coleta", date.today().isoformat())
    log(f"coleta: {novos} posts novos")
    return novos


SCHEMA_TRIAGEM = {
    "type": "object",
    "properties": {
        "comentar": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "resumo_pt": {"type": "string"}, "por_que_pt": {"type": "string"},
            "reacao": {"type": "string"},
            "variantes": {"type": "array", "items": {"type": "object", "properties": {
                "padrao": {"type": "string"}, "texto": {"type": "string"}}, "required": ["padrao", "texto"]}}},
            "required": ["id", "resumo_pt", "por_que_pt", "reacao", "variantes"]}},
        "curtir": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "motivo_pt": {"type": "string"}}, "required": ["id", "motivo_pt"]}},
    },
    "required": ["comentar", "curtir"],
}


def curtir_comentar(cfg, db, env, tg, perfil, dry=False):
    if kv_get(db, "ultima_coleta") != date.today().isoformat():
        coleta(cfg, db, env, dry)
    m = cfg["metas"]
    candidatos = db.execute(
        "SELECT * FROM posts WHERE status='novo' ORDER BY coalesce(data_post, coletado_em) DESC LIMIT 40").fetchall()
    if len(candidatos) < m["comentar_por_dia"]:
        tg.enviar("⚠️ <b>Rotina LinkedIn</b>: poucos posts novos hoje "
                  f"({len(candidatos)}). Veja o feed manualmente ou mande /configurar para ajustar os temas.")
        if not candidatos:
            return
    agora = datetime.now(timezone.utc)
    lista = []
    for p in candidatos:
        idade = round((agora - datetime.fromisoformat(p["data_post"])).total_seconds() / 3600, 1) if p["data_post"] else None
        lista.append({"id": p["id"], "author": p["autor"], "author_headline": p["headline"], "age_hours": idade,
                      "reactions": p["reacoes"], "comments": p["comentarios"], "text": p["texto"][:1500]})
    prompt = montar_prompt("prompts/triagem.md", perfil,
                           N_COMENTAR=m["comentar_por_dia"], N_CURTIR=m["curtir_por_dia"],
                           POSTS=json.dumps(lista, ensure_ascii=False, indent=1))
    res = claude(prompt, SCHEMA_TRIAGEM, cfg)
    por_id = {p["id"]: p for p in candidatos}

    comentar = [c for c in res["comentar"] if c["id"] in por_id][: m["comentar_por_dia"]]
    usados = {c["id"] for c in comentar}
    curtir = [c for c in res["curtir"] if c["id"] in por_id and c["id"] not in usados][: m["curtir_por_dia"]]

    if curtir:
        linhas = [f"👍 <b>CURTIR ({len(curtir)})</b> · meta do dia: {m['curtir_por_dia']}", ""]
        for i, c in enumerate(curtir, 1):
            p = por_id[c["id"]]
            linhas.append(f"{i}. <a href=\"{esc(p['url'])}\">{esc(p['autor'] or 'post')}</a>: {esc(c['motivo_pt'])}")
        enviar_tarefa(tg, db, "curtir", len(curtir), "\n".join(linhas), ",".join(c["id"] for c in curtir))

    for i, c in enumerate(comentar, 1):
        p = por_id[c["id"]]
        texto = [f"💬 <b>COMENTAR {i}/{len(comentar)}</b>",
                 f"👤 {esc(p['autor'])}" + (f" · <i>{esc(p['headline'][:120])}</i>" if p["headline"] else ""),
                 f"🔗 {esc(p['url'])}",
                 f"📝 {esc(c['resumo_pt'])}",
                 f"🎯 {esc(c['por_que_pt'])}",
                 f"👍 Reação: <b>{esc(c['reacao'])}</b>", ""]
        for j, v in enumerate(c["variantes"][:2], 1):
            alerta = "" if 200 <= len(v["texto"]) <= 350 else f" ⚠️ {len(v['texto'])} caracteres"
            texto += [f"<b>Opção {j}</b> ({esc(v['padrao'])}){alerta}", f"<code>{esc(v['texto'])}</code>", ""]
        texto.append("Toque no texto para copiar. Responda quem comentar de volta em até 24 h.")
        enviar_tarefa(tg, db, "comentar", 1, "\n".join(texto), c["id"])

    if dry:
        return
    for pid in usados:
        db.execute("UPDATE posts SET status='comentar' WHERE id=?", (pid,))
    for c in curtir:
        db.execute("UPDATE posts SET status='curtir' WHERE id=?", (c["id"],))
    for p in candidatos:  # o que não foi escolhido hoje não volta amanhã
        db.execute("UPDATE posts SET status='descartado' WHERE id=? AND status='novo'", (p["id"],))
    db.commit()
    log(f"curtir_comentar: {len(curtir)} curtir, {len(comentar)} comentar")


SCHEMA_PESSOAS = {
    "type": "object",
    "properties": {
        "pessoas": {"type": "array", "items": {"type": "object", "properties": {
            "grupo": {"type": "string"}, "nome": {"type": "string"}, "cargo": {"type": "string"},
            "url": {"type": "string"}, "motivo": {"type": "string"}},
            "required": ["grupo", "nome", "cargo", "url", "motivo"]}},
        "bloqueado": {"type": "boolean"},
        "alerta": {"type": "string"},
    },
    "required": ["pessoas", "bloqueado"],
}


def conectar(cfg, db, env, tg, perfil, dry=False):
    pc = cfg["pessoas"]
    blocos = []
    for g in pc["grupos"]:
        pagina = int(kv_get(db, f"pagina_{g['nome']}", 1))
        urls = []
        for n in range(pagina, pagina + pc["max_paginas_por_grupo"]):
            q = {"keywords": g["keywords"], "network": json.dumps(["S", "O"], separators=(",", ":")), "page": n, "origin": "FACETED_SEARCH"}
            if g["geo_urns"]:
                q["geoUrn"] = json.dumps(g["geo_urns"], separators=(",", ":"))
            urls.append("https://www.linkedin.com/search/results/people/?" + urllib.parse.urlencode(q))
        if not dry:
            kv_set(db, f"pagina_{g['nome']}", 1 if pagina >= 20 else pagina + pc["max_paginas_por_grupo"])
        blocos.append(f"- group \"{g['nome']}\": target {g['qtd']} people. Who: {g['descricao']}\n"
                      + "\n".join(f"  {u}" for u in urls))
    ja = [r["url"] for r in db.execute("SELECT url FROM pessoas")]
    prompt = montar_prompt("prompts/pessoas.md", perfil, MAX_PAGINAS=pc["max_paginas_por_grupo"],
                           GRUPOS="\n".join(blocos), JA_SUGERIDOS="\n".join(ja) or "(none)")
    res = claude(prompt, SCHEMA_PESSOAS, cfg, extra=CHROME)
    vistos = set(ja)
    for g in pc["grupos"]:
        lista = []
        for p in res["pessoas"]:
            url = p["url"].split("?")[0].rstrip("/") + "/"
            if p["grupo"] == g["nome"] and "/in/" in url and url not in vistos and len(lista) < g["qtd"]:
                vistos.add(url)
                lista.append({**p, "url": url})
        if not lista:
            continue
        linhas = [f"🤝 <b>CONECTAR · {len(lista)} {esc(g.get('rotulo', g['nome']))}</b>",
                  "Convite <b>sem nota</b>. Escreva só depois que a pessoa aceitar.", ""]
        for i, p in enumerate(lista, 1):
            linhas.append(f"{i}. <a href=\"{esc(p['url'])}\">{esc(p['nome'])}</a> · {esc(p['cargo'][:90])}\n   ↳ {esc(p['motivo'])}")
            if not dry:
                db.execute("INSERT OR IGNORE INTO pessoas VALUES(?,?,?,?,?)",
                           (p["url"], p["nome"], p["cargo"], g["nome"], date.today().isoformat()))
        enviar_tarefa(tg, db, "conectar", len(lista), "\n".join(linhas), g["nome"])
    db.commit()
    if res["bloqueado"] and not dry:
        pausar(tg, "o LinkedIn mostrou um aviso na busca de pessoas: " + res.get("alerta", ""))
    elif res.get("alerta"):
        tg.enviar("⚠️ <b>Aviso na busca de pessoas</b>: " + esc(res["alerta"]))
    log(f"conectar: {len(res['pessoas'])} pessoas retornadas; bloqueado={res['bloqueado']} alerta={res.get('alerta')!r}")


def responder(cfg, db, env, tg, perfil, dry=False):
    hoje = date.today().isoformat()
    feitos = db.execute("SELECT tipo, sum(qtd) n FROM tarefas WHERE status='feito' AND criado_em LIKE ? GROUP BY tipo",
                        (hoje + "%",)).fetchall()
    n = {r["tipo"]: r["n"] for r in feitos}
    m = cfg["metas"]
    msgs = json.loads(ler("dados/mensagens.json"))
    texto = (
        "📨 <b>RESPONDER</b>: mensagens e convites\n\n"
        "1. Aceite os convites relevantes: https://www.linkedin.com/mynetwork/invitation-manager/\n"
        "2. Responda todas as mensagens: https://www.linkedin.com/messaging/\n"
        "3. Responda quem comentou nos seus posts e quem respondeu aos seus comentários.\n\n"
        f"<b>Após o aceite (geral):</b>\n<code>{esc(msgs['geral'])}</code>\n\n"
        f"<b>Após o aceite (recrutador):</b>\n<code>{esc(msgs['recrutador'])}</code>\n\n"
        f"📊 Hoje (marcados como feitos): curtidas {n.get('curtir', 0)}/{m['curtir_por_dia']} · "
        f"comentários {n.get('comentar', 0)}/{m['comentar_por_dia']} · "
        f"conexões {n.get('conectar', 0)}/{m['conectar_recrutadores'] + m['conectar_area']}"
    )
    enviar_tarefa(tg, db, "responder", 1, texto)


SCHEMA_POST = {
    "type": "object",
    "properties": {
        "tema": {"type": "string"}, "formula_gancho": {"type": "string"}, "texto": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "primeiro_comentario": {"type": "string"},
        "imagem": {"type": "object", "properties": {"descricao_pt": {"type": "string"}, "texto_na_imagem": {"type": "string"}},
                   "required": ["descricao_pt", "texto_na_imagem"]},
        "horario_sugerido": {"type": "string"},
        "auditoria": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tema", "formula_gancho", "texto", "hashtags", "primeiro_comentario", "imagem", "horario_sugerido", "auditoria"],
}


def publicar(cfg, db, env, tg, perfil, dry=False):
    temas = [r["tema"] for r in db.execute("SELECT tema FROM publicacoes ORDER BY id")]
    prompt = montar_prompt("prompts/post.md", perfil,
                           TEMAS_USADOS="\n".join(f"- {t}" for t in temas) or "(none yet)")
    res = claude(prompt, SCHEMA_POST, cfg)
    corpo = res["texto"].strip()
    tags = " ".join(t if t.startswith("#") else "#" + t for t in res["hashtags"][:5])
    alerta = "" if 900 <= len(corpo) <= 1300 else f" ⚠️ fora da faixa 900–1.300"
    cabecalho = (
        f"📝 <b>PUBLICAR</b>: post de hoje\n\n"
        f"🧭 Tema: {esc(res['tema'])}\n🪝 Gancho: {esc(res['formula_gancho'])}\n"
        f"⏰ Horário sugerido: {esc(res['horario_sugerido'])}\n📏 {len(corpo)} caracteres{alerta}\n\n"
        f"🖼 <b>Imagem sugerida</b>: {esc(res['imagem']['descricao_pt'])}\n"
        f"Texto na imagem: <code>{esc(res['imagem']['texto_na_imagem'])}</code>\n\n"
        f"🔎 Auditoria: {esc('; '.join(res['auditoria']) or 'ok')}\n\n"
        "Próximas mensagens: 1) texto do post, 2) primeiro comentário. Depois de publicar, "
        "responda a todo comentário na 1ª hora."
    )
    tg.enviar(cabecalho)
    tg.enviar(corpo + "\n\n" + tags, html_mode=False)
    enviar_tarefa(tg, db, "publicar", 1, "💬 <b>Primeiro comentário</b> (publique logo após o post):\n\n<code>"
                  + esc(res["primeiro_comentario"]) + "</code>", res["tema"])
    if not dry:
        db.execute("INSERT INTO publicacoes(tema, texto, criado_em) VALUES(?,?,?)",
                   (res["tema"], corpo, datetime.now().isoformat(timespec="seconds")))
        db.commit()


def resumo(cfg, db, env, tg, perfil, dry=False):
    inicio = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    linhas = db.execute(
        "SELECT tipo, status, sum(qtd) n FROM tarefas WHERE criado_em >= ? GROUP BY tipo, status", (inicio,)).fetchall()
    t: dict = {}
    for r in linhas:
        t.setdefault(r["tipo"], {})[r["status"]] = r["n"]
    m = cfg["metas"]
    metas = {"curtir": m["curtir_por_dia"] * 5, "comentar": m["comentar_por_dia"] * 5,
             "conectar": (m["conectar_recrutadores"] + m["conectar_area"]) * 5, "publicar": m["posts_por_semana"]}
    nomes = {"curtir": "Curtidas", "comentar": "Comentários", "conectar": "Conexões", "publicar": "Posts"}
    texto = [f"📊 <b>RESUMO DA SEMANA</b> (desde {inicio})", ""]
    for k, nome in nomes.items():
        s = t.get(k, {})
        texto.append(f"{nome}: <b>{s.get('feito', 0)}</b>/{metas[k]} feitos · {s.get('pulado', 0)} pulados · "
                     f"{s.get('pendente', 0)} sem marcação")
    texto += ["", "Anote no LinkedIn (Analytics): visualizações do perfil, aparições em buscas e impressões."]
    if perfil.get("linha_base"):
        texto.append(f"Linha de base em {perfil.get('configurado_em', '')}: {esc(perfil['linha_base'])}")
    tg.enviar("\n".join(texto))


COMANDOS = "Comandos: /pausar · /religar · /configurar · /atualizar · /versao · /ajuda"
AJUDA = ("ℹ️ <b>Comandos</b>\n"
         "/pausar: para de mandar tarefas (férias, por exemplo)\n"
         "/religar: volta ao normal\n"
         "/configurar: refaz a personalização a partir do seu perfil\n"
         "/atualizar: instala a versão mais nova do robô, se houver\n"
         "/versao: mostra a versão instalada\n\n"
         "Nas tarefas, toque em ✅ Feito ou ⏭ Pular: é assim que o resumo da semana é contado.\n"
         "O robô só sugere; curtir, comentar, conectar e publicar é sempre com você.")


REINICIAR = False  # depois de atualizar, o ouvinte com o código antigo se encerra


def atualizar_agora(tg: Telegram, db, cfg, esperar: bool = False) -> bool:
    """Confere o GitHub e, se houver versão nova, troca o código e religa o robô."""
    try:
        info = atualizar.tem_nova(BASE, cfg["repositorio"])
        if not info:
            tg.enviar(f"✅ Você já está na versão mais nova ({atualizar.versao_local(BASE)}).")
            return False
        tg.enviar(f"⬆️ Atualizando para a versão <b>{esc(info['versao'])}</b>…")
        atualizar.aplicar(BASE, info, log)
    except Exception as e:
        log(f"atualizar: ERRO {e!r}")
        tg.enviar(f"❌ A atualização não deu certo e nada foi trocado.\n<code>{esc(str(e)[:500])}</code>")
        return False
    global REINICIAR
    kv_set(db, "atualizacao_pendente", info["versao"])
    tg.enviar("Arquivos atualizados. Religando o robô; a confirmação chega em alguns minutos.")
    try:
        atualizar.reiniciar(BASE, esperar)
    except Exception as e:  # o ouvinte se encerra mesmo assim e a tarefa o religa com o código novo
        log(f"atualizar: não consegui disparar o agendar.ps1: {e!r}")
    REINICIAR = True
    return True


def checar_versao_do_dia(tg: Telegram, db, cfg):
    """Uma vez por dia: se houver versão nova ainda não avisada, manda o aviso com o botão."""
    hoje = date.today().isoformat()
    if kv_get(db, "ultima_checagem") == hoje or datetime.now().hour < 9:
        return
    kv_set(db, "ultima_checagem", hoje)
    info = atualizar.tem_nova(BASE, cfg["repositorio"])
    if info and kv_get(db, "versao_avisada") != info["versao"]:
        kv_set(db, "versao_avisada", info["versao"])
        notas = info["notas"].strip()[:1500] or "Melhorias gerais."
        tg.enviar(f"🆕 <b>Versão {esc(info['versao'])} disponível</b> (você está na {esc(atualizar.versao_local(BASE))})\n\n"
                  f"{esc(notas)}\n\nSeus dados e configurações são mantidos.",
                  [[("⬆️ Atualizar", f"u:{info['versao']}")]])


def escutar(cfg, db, env, tg):
    """Fica ligado em segundo plano confirmando os cliques e lendo os comandos na hora."""
    t = trava(cfg)
    if not t:
        log("ouvinte: já existe um ligado; esta cópia vai fechar")
        return
    log(f"ouvinte: ligado (versão {atualizar.versao_local(BASE)})")
    pendente = kv_get(db, "atualizacao_pendente")
    if pendente:  # o ouvinte novo confirma que o código atualizado está rodando
        db.execute("DELETE FROM kv WHERE k='atualizacao_pendente'")
        db.commit()
        tg.enviar(f"✅ <b>Versão {esc(atualizar.versao_local(BASE))} ativa.</b> Tudo certo por aqui.")
    while True:
        try:
            kv_set(db, "ouvinte_batida", datetime.now().isoformat(timespec="seconds"))
            try:
                checar_versao_do_dia(tg, db, cfg)
            except Exception as e:
                log(f"ouvinte: não consegui conferir versão nova: {e!r}")
            for texto in processar_updates(tg, db, espera=50):
                comando = texto.split()[0].lower().split("@")[0]
                if comando == "/configurar":
                    try:
                        configurar(cfg, db, env, tg)
                        cfg = carregar_config()
                    except Exception as e:
                        log(f"configurar: ERRO {e!r}")
                        tg.enviar(f"❌ Erro na configuração: <code>{esc(str(e)[:500])}</code>\nMande /configurar para tentar de novo.")
                elif comando == "/atualizar":
                    atualizar_agora(tg, db, cfg)
                elif comando == "/versao":
                    tg.enviar(f"ℹ️ Versão instalada: <b>{esc(atualizar.versao_local(BASE))}</b>")
                elif comando == "/pausar":
                    pausar(tg, "pedido por você")
                elif comando == "/religar":
                    (BASE / "PAUSADO").unlink(missing_ok=True)
                    tg.enviar("▶️ Robô religado.")
                else:  # /ajuda, /start ou qualquer outro texto
                    tg.enviar(AJUDA)
            if REINICIAR:  # a tarefa RoboLinkedIn\ouvinte liga a cópia nova em até 10 minutos, se o agendar.ps1 não ligar antes
                log("ouvinte: encerrando para rodar o código novo")
                return
        except Exception as e:
            log(f"ouvinte: erro {e!r}")
            time.sleep(30)


MOMENTOS = {"curtir_comentar": curtir_comentar, "conectar": conectar, "responder": responder,
            "publicar": publicar, "resumo": resumo}


def main():
    for stream in (sys.stdout, sys.stderr):  # Agendador redireciona para arquivo em cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("momento", choices=["vincular", "definir", "checar", "configurar", "teste", "pronto", "coleta",
                                        "status", "escutar", "config", "versao", "atualizar", *MOMENTOS])
    ap.add_argument("alvo", nargs="?", help="checar: claude|chrome|apify|telegram · definir: nome da chave")
    ap.add_argument("--dry-run", action="store_true", help="imprime na tela em vez de enviar ao Telegram")
    a = ap.parse_args()
    if a.momento == "definir":  # o valor vem pela entrada padrão para não ficar no histórico do terminal
        return gravar_env(a.alvo, sys.stdin.readline().strip())
    if a.momento == "config":  # configuração combinada, lida pelo agendar.ps1
        return print(json.dumps(carregar_config(), ensure_ascii=False))
    if a.momento == "versao":
        return print(atualizar.versao_local(BASE))
    env = carregar_env()
    cfg = carregar_config()
    db = abrir_db()
    if a.momento == "vincular":
        return vincular(env, db)
    tg = Telegram(env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID"), dry_run=a.dry_run)
    if a.momento == "escutar":
        return escutar(cfg, db, env, tg)
    perfil = carregar_perfil()
    if a.momento in MOMENTOS or a.momento == "coleta":
        if (BASE / "PAUSADO").exists():
            log(f"{a.momento}: robô pausado (arquivo PAUSADO existe)")
            return
        if not perfil:
            log(f"{a.momento}: robô ainda não configurado (falta dados/perfil.json); rode o configurar")
            return
    try:
        if a.momento == "checar":
            return checar(a.alvo, cfg, env, tg)
        if a.momento == "atualizar":  # ATUALIZAR.cmd: mesmo caminho do /atualizar do Telegram
            print(f"Versão instalada: {atualizar.versao_local(BASE)}. Conferindo o GitHub...")
            atualizar_agora(tg, db, cfg, esperar=True)
            return print(f"Versão agora: {atualizar.versao_local(BASE)}")
        if a.momento == "configurar":
            t = trava(cfg)  # durante a configuração, o ouvinte não pode ler o Telegram ao mesmo tempo
            if not t and not a.dry_run:
                raise RuntimeError("o ouvinte está ligado: mande /configurar no Telegram em vez de rodar aqui")
            return configurar(cfg, db, env, tg, a.dry_run)
        processar_updates(tg, db)
        if a.momento == "teste":
            tg.enviar("✅ <b>Robô da rotina LinkedIn</b> conectado. Este é um teste.", botoes(0))
        elif a.momento == "pronto":
            h = cfg["horarios"]
            tg.enviar("🗓 <b>Tudo pronto!</b> Seus horários:\n"
                      f"• Seg a sex {h['curtir_comentar']}: curtir e comentar\n"
                      f"• Seg a sex {h['conectar']}: conectar\n"
                      f"• Seg a sex {h['responder']}: responder\n"
                      f"• {h['publicar_dias']} {h['publicar']}: post\n"
                      f"• {h['resumo_dia']} {h['resumo']}: resumo da semana\n\n"
                      "O computador precisa estar ligado, com a sua sessão do Windows aberta e o Chrome aberto nesses horários.\n"
                      + COMANDOS)
        elif a.momento == "coleta":
            coleta(cfg, db, env, a.dry_run)
        elif a.momento == "status":
            for r in db.execute("SELECT status, count(*) n FROM posts GROUP BY status"):
                print(f"posts {r['status']}: {r['n']}")
            for r in db.execute("SELECT tipo, status, count(*) n FROM tarefas GROUP BY tipo, status"):
                print(f"tarefas {r['tipo']}/{r['status']}: {r['n']}")
        else:
            MOMENTOS[a.momento](cfg, db, env, tg, perfil, a.dry_run)
        log(f"{a.momento}: ok")
    except Exception as e:
        log(f"{a.momento}: ERRO {e!r}")
        if not a.dry_run and tg.chat_id:
            try:
                tg.enviar(f"❌ <b>Robô LinkedIn</b>: erro no momento <b>{esc(a.momento)}</b>\n<code>{esc(str(e)[:800])}</code>")
            except Exception:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
