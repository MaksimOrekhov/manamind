"""Small Tkinter always-on-top presentation for the existing read-only LIVE runtime."""
from __future__ import annotations

import json
from pathlib import Path

from .recommendation import Recommendation

_STATUS_TEXT = {
    "DISCONNECTED": "Ожидание Power.log · отключено",
    "WAITING_FOR_GAME": "Ожидание игры",
    "SYNCING": "Синхронизация состояния",
    "READY": "Доверенное решение SELF",
    "UNTRUSTED": "Состояние не подтверждено",
    "GAME_OVER": "Матч завершён",
}
_ACTION_TEXT = {
    "PLAY_CARD": "Разыграть карту",
    "ATTACK": "Атаковать",
    "HERO_POWER": "Использовать силу героя",
    "ACTIVATE_LOCATION": "Активировать локацию",
    "END_TURN": "Завершить ход",
}


def load_card_names(path: Path) -> dict[str, str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    records = payload.get("cards", []) if isinstance(payload, dict) else payload
    return {record["id"]: record["name"] for record in records
            if isinstance(record, dict) and record.get("id") and record.get("name")}


def _card_name(card_id: str | None, names: dict[str, str]) -> str:
    if not card_id:
        return "неизвестная карта"
    return names.get(card_id, f"{card_id} (имя неизвестно)")


def describe_action(action: dict, names: dict[str, str]) -> str:
    """Render action identity and board/hand position without exposing entity handles."""
    kind = action.get("type", "UNKNOWN_ACTION")
    label = _ACTION_TEXT.get(kind, kind)
    if kind == "END_TURN":
        return label
    if kind == "PLAY_CARD":
        card_id = action.get("card_id")
        card_type = action.get("card_type", "тип неизвестен")
        hand_index = action.get("hand_index")
        text = f"{label}: {_card_name(card_id, names)} · {card_type}"
        if type(hand_index) is int:
            text += f" · рука #{hand_index + 1}"
        position = action.get("play_position", 0)
        if type(position) is int and position > 0:
            text += f" · слот стола #{position}"
        return text

    source_id = action.get("source_card_id") or action.get("card_id")
    if action.get("source_is_hero"):
        source = "ваш герой"
    else:
        source = _card_name(source_id, names)
        board_position = action.get("source_board_position")
        if type(board_position) is int and board_position > 0:
            source += f" · стол #{board_position}"
    text = f"{label}: {source}"
    if action.get("target_kind"):
        side = "ваша" if action.get("target_side") == "SELF" else "противника"
        if action.get("target_kind") == "HERO":
            target = f"герой {side}"
        else:
            target = f"{side} цель {_card_name(action.get('target_card_id'), names)}"
            position = action.get("target_board_position")
            if type(position) is int and position > 0:
                target += f" · стол #{position}"
        text += f" → {target}"
    return text


class OverlayPanel:
    def __init__(self, root, tkinter, names: dict[str, str]) -> None:
        self.root = root
        self.tk = tkinter
        self.names = names
        root.title("ManaMind · экспериментальная Policy")
        root.geometry("560x370+40+180")
        root.minsize(460, 300)
        root.attributes("-topmost", True)
        root.configure(background="#151923")
        self.status = tkinter.Label(root, text="Запуск ManaMind…", anchor="w", justify="left",
                                    font=("Segoe UI", 11, "bold"), fg="#9bd2ff", bg="#151923")
        self.status.pack(fill="x", padx=16, pady=(16, 6))
        self.turn = tkinter.Label(root, text="", anchor="w", font=("Segoe UI", 10),
                                  fg="#d9e2f2", bg="#151923")
        self.turn.pack(fill="x", padx=16, pady=4)
        self.advice = tkinter.Label(root, text="Подсказки пока недоступны.", anchor="nw", justify="left",
                                    wraplength=525, font=("Segoe UI", 10), fg="#f4f6fb", bg="#151923")
        self.advice.pack(fill="both", expand=True, padx=16, pady=10)
        self.footer = tkinter.Label(root, text="Экспериментальная Policy · порядок действий, не вероятность победы",
                                    anchor="w", justify="left", wraplength=525,
                                    font=("Segoe UI", 8), fg="#aab5c5", bg="#151923")
        self.footer.pack(fill="x", padx=16, pady=(4, 12))

    def on_message(self, message: str) -> None:
        if message.startswith("status: "):
            detail = message[8:]
            status = detail.split(" ", 1)[0].split("(", 1)[0]
            if status == "SYNCING" and "(AWAITING_DECISION)" in detail:
                status_text = "Ожидание следующего решения"
            else:
                status_text = _STATUS_TEXT.get(status, detail)
            self.status.configure(text=status_text)
            if status != "READY":
                self.turn.configure(text="")
                self.advice.configure(text="Рекомендации скрыты до следующего доверенного решения SELF.")
        elif " invalidated" in message:
            self.turn.configure(text="")
            self.advice.configure(text="Рейтинг устарел и скрыт. Ожидание нового решения.")
        elif message.startswith("no recommendation:"):
            self.turn.configure(text="")
            self.advice.configure(text=f"Подсказка недоступна: {message.partition(':')[2].strip()}")
        elif "recommendation warning:" in message:
            self.turn.configure(text="")
            self.advice.configure(text="Policy v2 недоступна. Проверьте checkpoint и локальный каталог карт.")
        elif message.startswith("LIVE warning:"):
            self.turn.configure(text="")
            self.advice.configure(text="LIVE чтение остановлено; сбор завершённых матчей продолжает retry.")

    def on_recommendation(self, recommendation: Recommendation) -> None:
        self.turn.configure(text=f"Ход {recommendation.turn} · {recommendation.menu_size} допустимых вариантов")
        lines = [f"#{rank}  {describe_action(item.action, self.names)}"
                 for rank, item in enumerate(recommendation.ranked, 1)]
        self.advice.configure(text="\n\n".join(lines) if lines else "У рекомендации нет вариантов.")


def launch_overlay(runtime, cards_path: Path, poll_ms: int = 50) -> None:
    """Run the UI and the already-created LIVE/collector runtime in one process."""
    import tkinter as tkinter

    root = tkinter.Tk()
    try:
        names = load_card_names(cards_path)
    except (OSError, ValueError, KeyError, TypeError):
        names = {}
    panel = OverlayPanel(root, tkinter, names)
    original_emit = runtime.emit

    def emit(message: str) -> None:
        original_emit(message)
        panel.on_message(message)

    runtime.emit = emit
    runtime.on_recommendation = panel.on_recommendation

    def tick() -> None:
        if not root.winfo_exists():
            return
        runtime.step()
        root.after(poll_ms, tick)

    def close() -> None:
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    runtime.emit(f"status: {runtime.live.session.status.value}")
    runtime.emit("ManaMind read-only panel. Close this window to stop.")
    if runtime.recommender is None:
        panel.on_message(f"recommendation warning: {runtime.recommender_unavailable or 'UNAVAILABLE'}")
    root.after(0, tick)
    root.mainloop()
