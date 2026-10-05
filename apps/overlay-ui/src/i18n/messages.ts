/**
 * Overlay-owned strings only. Card and action names are NOT here: future
 * runtime DTOs are expected to carry display-ready, already localized labels.
 */
const en = {
  'status.idle': 'Idle',
  'status.thinking': 'Analyzing',
  'status.ready': 'Ready',
  'status.waiting': 'Waiting',
  'status.error': 'Error',

  'msg.idle': 'No active Hearthstone match',
  'msg.thinking': 'Analyzing position…',
  'msg.waiting': 'Waiting for opponent…',
  'msg.error': 'Runtime error. No recommendation is shown.',

  'badge.exact': 'EXACT',
  'badge.inferred': 'INFERRED',
  'badge.neural': 'NEURAL',
  'badge.unavailable': 'N/A',

  'summary.exact': 'Exact simulation',
  'summary.inferred': 'Inferred simulation · evidence debt',
  'summary.neural': 'Neural fallback',
  'summary.unavailable': 'Engine could not simulate action',

  'note.inferredDone': 'Inferred simulation · evidence debt',
  'note.noExactChild': 'No exact child state',
  'note.rulesNotVerified': 'Rules not fully verified',
  'note.fallbackEligible': 'Fallback eligible',

  'count.exact': 'Exact',
  'count.inferred': 'Inferred',
  'count.neural': 'Neural',
  'count.unavailable': 'Unavailable',

  'turn': 'Turn',
  'latency': 'Latency',
  'unit.ms': 'ms',
  'unit.s': 's',

  'a11y.panel': 'ManaMind recommendations',
  'a11y.list': 'Recommended actions',
  'a11y.winProbability': 'Win probability',
  'a11y.sourceSummary': 'Evaluation source summary',
  'a11y.language': 'Language',
} as const

export type MessageKey = keyof typeof en

const ru: Record<MessageKey, string> = {
  'status.idle': 'Ожидание',
  'status.thinking': 'Анализ',
  'status.ready': 'Готово',
  'status.waiting': 'Ждём',
  'status.error': 'Ошибка',

  'msg.idle': 'Нет активного матча Hearthstone',
  'msg.thinking': 'Анализирую позицию…',
  'msg.waiting': 'Ожидание хода соперника…',
  'msg.error': 'Ошибка выполнения. Рекомендации не показаны.',

  'badge.exact': 'ТОЧНО',
  'badge.inferred': 'С ДОПУЩ.',
  'badge.neural': 'НЕЙРО',
  'badge.unavailable': 'Н/Д',

  'summary.exact': 'Точный расчёт движком',
  'summary.inferred': 'Расчёт с допущениями · правила подтверждены не полностью',
  'summary.neural': 'Оценка нейросетью',
  'summary.unavailable': 'Движок не смог рассчитать этот ход',

  'note.inferredDone': 'Расчёт выполнен с допущениями',
  'note.noExactChild': 'Точный результат хода не рассчитан',
  'note.rulesNotVerified': 'Правила подтверждены не полностью',
  'note.fallbackEligible': 'Допустима запасная оценка',

  'count.exact': 'Точно',
  'count.inferred': 'С допущ.',
  'count.neural': 'Нейро',
  'count.unavailable': 'Недоступно',

  'turn': 'Ход',
  'latency': 'Задержка',
  'unit.ms': 'мс',
  'unit.s': 'с',

  'a11y.panel': 'Рекомендации ManaMind',
  'a11y.list': 'Рекомендуемые действия',
  'a11y.winProbability': 'Вероятность победы',
  'a11y.sourceSummary': 'Сводка по источникам оценки',
  'a11y.language': 'Язык',
}

export const messages = { en, ru } as const
