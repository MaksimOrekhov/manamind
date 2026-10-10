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

_REASON_TEXT = {
    "AMBIGUOUS_SELECTION": "Не удалось однозначно распознать доступные действия.",
    "INCOMPLETE_MENU": "Не удалось надёжно построить полный список доступных действий.",
    "MENU_KIND_MISMATCH": "Состав доступных действий не удалось сопоставить с текущим состоянием.",
    "UNSUPPORTED_ACTION": "В списке есть действие, которое текущая версия не может обработать.",
    "INVALID_PUBLIC_CARD_ID": "Не удалось проверить карту в списке доступных действий.",
    "MENU_TARGET_MISMATCH": "Не удалось проверить цель одного из доступных действий.",
    "CHECKPOINT_IDENTITY_MISMATCH": "Контрольная сумма Policy не совпадает с ожидаемой.",
    "CHECKPOINT_INCOMPATIBLE": "Checkpoint Policy несовместим с текущей версией приложения.",
    "RUNTIME_CATALOG_MISMATCH": "Каталог карт несовместим с checkpoint Policy.",
    "INVALID_MODEL_OUTPUT": "Policy вернула результат, который нельзя безопасно показать.",
    "INFERENCE_FAILED": "Не удалось рассчитать рейтинг Policy.",
    "OPTIONS_CHANGED": "Список доступных действий изменился во время расчёта; результат отброшен.",
    "DECISION_CHANGED_DURING_INFERENCE": "Игровое решение изменилось во время расчёта; результат отброшен.",
    "NOT_CURRENT_READY_SELF": "Сейчас нет подтверждённого решения вашего хода.",
    "UNTRUSTED_OR_UNSETTLED": "Состояние игры пока не подтверждено; рекомендации скрыты.",
    "PRIVACY_OR_STATE_MISMATCH": "Состояние не прошло проверку безопасности; рекомендация скрыта.",
}

_TRUST_REASONS = {
    "PARSE_ERROR": "Состояние игры не удалось разобрать; рекомендации скрыты.",
    "INVARIANT": "Данные состояния игры противоречат друг другу; рекомендации скрыты.",
    "SELF_AMBIGUOUS": "Не удалось определить сторону игрока; рекомендации скрыты.",
    "ENTITY_UNKNOWN": "Не удалось сопоставить игровые сущности; рекомендации скрыты.",
    "UNSUPPORTED_MODE": "Режим игры не поддерживается; рекомендации скрыты.",
    "MODE_AMBIGUOUS": "Не удалось определить режим игры; рекомендации скрыты.",
    "SPECTATOR": "Режим наблюдателя не поддерживает рекомендации.",
    "FILE_DISCONTINUITY": "Поток Power.log прервался; состояние синхронизируется.",
    "RECONNECT": "Игра переподключилась; состояние синхронизируется.",
    "SETTLE_TIMEOUT": "Игра обновляет состояние; ожидается стабильное решение.",
    "AWAITING_SELF": "Ожидание вашего хода.",
    "AWAITING_DECISION": "Ожидание следующего решения.",
    "GAME_RESET": "Состояние матча сброшено; ожидается новая синхронизация.",
    "NO_POWER_LOG": "Power.log пока не найден.",
    "NO_LOGS_ROOT": "Папка журналов Hearthstone не найдена.",
    "UNREADABLE": "Power.log пока нельзя прочитать.",
}


def _reason_lines(reason: str) -> str:
    explanation = _REASON_TEXT.get(reason)
    if explanation is None:
        explanation = _TRUST_REASONS.get(reason)
    if explanation is None:
        explanation = "Рекомендация временно недоступна."
    return f"{explanation}\nКод: {reason}"


def _status_lines(status: str, reason: str | None) -> str:
    if status == "SYNCING" and reason == "AWAITING_DECISION":
        return _reason_lines(reason)
    if status == "SYNCING":
        return _reason_lines(reason) if reason else "Обновление игрового состояния."
    if status == "UNTRUSTED":
        return _reason_lines(reason) if reason else "Доверие к игровому состоянию потеряно; рекомендации скрыты."
    messages = {
        "DISCONNECTED": "Нет подключения к Power.log; ожидание журнала игры.",
        "WAITING_FOR_GAME": "Ожидание начала игры.",
        "GAME_OVER": "Матч завершён; рекомендации скрыты.",
        "READY": "Получено доверенное решение; подготовка рейтинга Policy.",
    }
    message = messages.get(status, "Состояние игры обновлено.")
    return f"{message}\nКод: {reason}" if reason else message


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
        self.last_status_signature: tuple[str, str | None] | None = None
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
            reason = detail.partition("(")[2].partition(")")[0] or None
            signature = (status, reason)
            status_text = ("Ожидание следующего решения" if status == "SYNCING" and reason == "AWAITING_DECISION"
                           else _STATUS_TEXT.get(status, status))
            self.status.configure(text=status_text)
            if status != "READY":
                self.turn.configure(text="")
                if getattr(self, "last_status_signature", None) != signature:
                    self.advice.configure(text=_status_lines(status, reason))
            elif getattr(self, "last_status_signature", None) != signature:
                self.turn.configure(text="")
                self.advice.configure(text=_status_lines(status, reason))
            self.last_status_signature = signature
        elif " invalidated" in message:
            self.turn.configure(text="")
            self.advice.configure(text="Рейтинг устарел и скрыт. Ожидание нового решения.")
        elif message.startswith("no recommendation:"):
            self.turn.configure(text="")
            reason = message.partition(":")[2].strip()
            self.advice.configure(text=_reason_lines(reason))
        elif "recommendation warning:" in message:
            self.turn.configure(text="")
            detail = message.partition(":")[2].split(";", 1)[0].strip() or "UNAVAILABLE"
            self.advice.configure(text=f"Policy v2 не удалось запустить. Проверьте checkpoint и каталог карт.\nКод: {detail}")
        elif message.startswith("LIVE warning:"):
            self.turn.configure(text="")
            detail = message.partition(":")[2].split(";", 1)[0].strip() or "LIVE_UNAVAILABLE"
            self.advice.configure(text=f"Не удалось читать игровой журнал; рекомендации отключены.\nКод: {detail}")

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
