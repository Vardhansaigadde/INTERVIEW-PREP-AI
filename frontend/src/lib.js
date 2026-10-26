export const STATE_META = {
  engaged: { label: 'Engaged', color: 'var(--state-engaged)' },
  neutral: { label: 'Neutral', color: 'var(--state-neutral)' },
  confused: { label: 'Confused', color: 'var(--state-confused)' },
  frustrated: { label: 'Frustrated', color: 'var(--state-frustrated)' },
  distracted: { label: 'Away', color: 'var(--state-distracted)' },
}

export const pct = (x) => `${Math.round(x * 100)}%`

export function masteryTone(t) {
  if (!t.attempts) return 'new'
  return t.mastery >= 0.75 ? 'good' : t.mastery >= 0.5 ? 'mid' : 'low'
}
