import type { Language, Status } from '../overlay/types'
const statuses: Record<Language, Record<Status, string>> = {
  ru: { DISCONNECTED: 'Нет подключения', WAITING_FOR_GAME: 'Ожидание игры', SYNCING: 'Обновление состояния',
    READY: 'Твой ход', UNTRUSTED: 'Состояние не подтверждено', GAME_OVER: 'Матч завершён',
    THINKING: 'Policy выбирает действие…', UNAVAILABLE: 'Рекомендация недоступна' },
  en: { DISCONNECTED: 'Disconnected', WAITING_FOR_GAME: 'Waiting for a game', SYNCING: 'Updating state',
    READY: 'Your turn', UNTRUSTED: 'State untrusted', GAME_OVER: 'Game over',
    THINKING: 'Policy is ranking actions…', UNAVAILABLE: 'Recommendation unavailable' },
}
export const statusText = (status: Status, language: Language) => statuses[language][status]
export const words = {
  ru: { details: 'Детали', close: 'Закрыть', collapse: 'Свернуть', restore: 'Развернуть', opacity: 'Непрозрачность',
    turn: 'Ход', footer: 'Нейросетевая Policy v2 · только совет', order: 'Все позиции — слева направо на твоём экране. Локации тоже занимают место.',
    waiting: 'Подсказки появятся после подтверждения нового решения.', checkpoint: 'Policy не загрузилась. Проверь checkpoint и каталог.',
    logit: 'Оценка ранжирования (logit), не вероятность победы', updated: 'Обновлено',
    flagButton: 'Рекомендация кажется сомнительной', flagged: 'Отмечено для разбора после матча',
    flagSaved: 'Отмечено. Разберёшь после матча.', flagStale: 'Решение уже изменилось. Новая отметка не создана.',
    flagFailed: 'Не удалось сохранить отметку. Попробуй ещё раз.' },
  en: { details: 'Details', close: 'Close', collapse: 'Collapse', restore: 'Expand', opacity: 'Opacity',
    turn: 'Turn', footer: 'Neural Policy v2 · advice only', order: 'Positions run left to right on your screen. Locations occupy a slot too.',
    waiting: 'Advice appears after a new decision is confirmed.', checkpoint: 'Policy failed to load. Check checkpoint and catalog.',
    logit: 'Ranking score (logit), not win probability', updated: 'Updated',
    flagButton: 'This recommendation seems questionable', flagged: 'Saved for review after the match',
    flagSaved: 'Saved. Review it after the match.', flagStale: 'The decision changed. No new flag was saved.',
    flagFailed: 'Could not save the flag. Try again.' },
}
