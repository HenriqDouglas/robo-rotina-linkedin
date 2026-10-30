"""Cliente mínimo da Bot API do Telegram (sem dependências além de requests)."""
from __future__ import annotations

import html

import requests

API = "https://api.telegram.org/bot{token}/{metodo}"
LIMITE = 4000  # a API aceita 4096; folga para as tags HTML


def esc(texto) -> str:
    return html.escape(str(texto or ""), quote=False)


class Telegram:
    def __init__(self, token: str, chat_id: str | None, dry_run: bool = False):
        self.token = token
        self.chat_id = str(chat_id) if chat_id else None
        self.dry_run = dry_run

    def _call(self, metodo: str, _timeout: float = 60, **params):
        r = requests.post(API.format(token=self.token, metodo=metodo), json=params, timeout=_timeout)
        dados = r.json()
        if not dados.get("ok"):
            raise RuntimeError(f"Telegram {metodo}: {dados.get('description')}")
        return dados["result"]

    def enviar(self, texto: str, botoes: list[list[tuple[str, str]]] | None = None, html_mode: bool = True):
        """Envia uma mensagem; corta em pedaços se passar do limite. Retorna o message_id da última."""
        if self.dry_run:
            print("\n----- TELEGRAM (dry-run) -----\n" + texto)
            if botoes:
                print("[botões] " + " | ".join(t for linha in botoes for t, _ in linha))
            return None
        partes = [texto[i:i + LIMITE] for i in range(0, len(texto), LIMITE)] or [""]
        msg = None
        for i, parte in enumerate(partes):
            params = {"chat_id": self.chat_id, "text": parte, "disable_web_page_preview": True}
            if html_mode:
                params["parse_mode"] = "HTML"
            if botoes and i == len(partes) - 1:
                params["reply_markup"] = {
                    "inline_keyboard": [[{"text": t, "callback_data": d} for t, d in linha] for linha in botoes]
                }
            msg = self._call("sendMessage", **params)
        return msg["message_id"] if msg else None

    def updates(self, offset: int | None, espera: int = 0):
        """espera > 0 = long polling: a chamada fica aberta até chegar um clique ou passar `espera` segundos."""
        params = {"timeout": espera, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", _timeout=espera + 30, **params)

    def responder_callback(self, callback_id: str, texto: str):
        self._call("answerCallbackQuery", callback_query_id=callback_id, text=texto)

    def marcar_mensagem(self, message_id: int, rotulo: str):
        """Troca os botões da mensagem por um rótulo de status."""
        self._call(
            "editMessageReplyMarkup",
            chat_id=self.chat_id,
            message_id=message_id,
            reply_markup={"inline_keyboard": [[{"text": rotulo, "callback_data": "x"}]]},
        )
