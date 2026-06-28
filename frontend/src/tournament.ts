export type QualificationState = 'qualified' | 'best-third' | 'out'
export type BracketScore = { home: number | null; away: number | null; winner?: string | null }

export function qualificationLabel(state: QualificationState): string {
  if (state === 'qualified') return 'Auto'
  if (state === 'best-third') return 'Best 3rd'
  return 'Out'
}

export function winnerTone(teamName: string, winner: string): 'winner' | 'challenger' {
  return teamName === winner ? 'winner' : 'challenger'
}

export function bracketScoreLabel(
  score?: BracketScore,
  status?: string,
): string {
  if (score?.home !== null && score?.home !== undefined && score?.away !== null && score?.away !== undefined) {
    return `${status === 'FINISHED' ? 'FT ' : ''}${score.home}-${score.away}`
  }
  return status ?? ''
}
