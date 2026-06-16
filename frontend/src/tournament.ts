export type QualificationState = 'qualified' | 'best-third' | 'out'

export function qualificationLabel(state: QualificationState): string {
  if (state === 'qualified') return 'Auto'
  if (state === 'best-third') return 'Best 3rd'
  return 'Out'
}

export function winnerTone(teamName: string, winner: string): 'winner' | 'challenger' {
  return teamName === winner ? 'winner' : 'challenger'
}
