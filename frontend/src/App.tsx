import { Activity, AlertTriangle, BarChart3, ChevronDown, ChevronRight, Plus, RefreshCcw, Target, Trophy } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { apiGet, DASHBOARD_POLL_INTERVAL_MS, type Fixture, type FixtureDetail, type Prediction, type Recommendations, type SyncStatus } from './api'
import { formatPercent, parlaySummary, recommendationSummary, strongestEdge, syncStatusSummary, teamStatSummary, type ParlayLeg } from './betting'
import { dateGroupKey, gameTimeLabel, groupFixturesByDate, kickoffLabel } from './fixtureGroups'

const outcomeLabels = {
  home: 'Home',
  draw: 'Draw',
  away: 'Away',
} as const

function App() {
  const [fixtures, setFixtures] = useState<Fixture[]>([])
  const [selectedId, setSelectedId] = useState<string>('')
  const [openDateGroups, setOpenDateGroups] = useState<Record<string, boolean>>({})
  const [prediction, setPrediction] = useState<Prediction | null>(null)
  const [fixtureDetail, setFixtureDetail] = useState<FixtureDetail | null>(null)
  const [recommendations, setRecommendations] = useState<Recommendations | null>(null)
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null)
  const [parlayLegs, setParlayLegs] = useState<ParlayLeg[]>([])
  const [error, setError] = useState<string>('')
  const [loading, setLoading] = useState(true)

  function loadFixtures() {
    return apiGet<Fixture[]>('/fixtures')
      .then((items) => {
        setFixtures(items)
        setSelectedId((current) => current || items[0]?.id || '')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }

  function loadRecommendations() {
    return apiGet<Recommendations>('/bets/recommendations')
      .then(setRecommendations)
      .catch((err: Error) => setError(err.message))
  }

  function loadSyncStatus() {
    return apiGet<SyncStatus>('/sync/status')
      .then(setSyncStatus)
      .catch((err: Error) => setError(err.message))
  }

  useEffect(() => {
    void loadFixtures()
    void loadRecommendations()
    void loadSyncStatus()
    const interval = window.setInterval(() => {
      void loadFixtures()
      void loadRecommendations()
      void loadSyncStatus()
    }, DASHBOARD_POLL_INTERVAL_MS)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    if (!selectedId) return
    function loadSelectedGame() {
      apiGet<Prediction>(`/predictions/${selectedId}`)
        .then(setPrediction)
        .catch((err: Error) => setError(err.message))
      apiGet<FixtureDetail>(`/fixtures/${selectedId}`)
        .then(setFixtureDetail)
        .catch((err: Error) => setError(err.message))
    }
    setPrediction(null)
    setFixtureDetail(null)
    loadSelectedGame()
    const interval = window.setInterval(loadSelectedGame, DASHBOARD_POLL_INTERVAL_MS)
    return () => window.clearInterval(interval)
  }, [selectedId])

  const selectedFixture = fixtures.find((fixture) => fixture.id === selectedId)
  const edge = prediction?.edges ? strongestEdge(prediction.edges) : null
  const parlay = useMemo(() => parlaySummary(parlayLegs), [parlayLegs])
  const recSummary = recommendations ? recommendationSummary(recommendations) : null
  const homeStats = teamStatSummary(fixtureDetail?.home_team_stats)
  const awayStats = teamStatSummary(fixtureDetail?.away_team_stats)
  const syncSummary = syncStatusSummary(syncStatus)
  const matrixCells = prediction?.score_matrix.filter((cell) => cell.score !== 'other').slice(0, 36) ?? []
  const fixtureDateGroups = useMemo(() => groupFixturesByDate(fixtures), [fixtures])

  useEffect(() => {
    const selected = fixtures.find((fixture) => fixture.id === selectedId)
    if (!selected) return
    const key = dateGroupKey(selected.kickoff)
    setOpenDateGroups((current) => (current[key] ? current : { ...current, [key]: true }))
  }, [fixtures, selectedId])

  function toggleDateGroup(key: string) {
    setOpenDateGroups((current) => ({ ...current, [key]: !current[key] }))
  }

  function addLeg(outcome: keyof typeof outcomeLabels) {
    if (!prediction?.edges || !selectedFixture) return
    const odds = prediction.edges[outcome].american_odds
    setParlayLegs((legs) => [
      ...legs,
      {
        label: `${selectedFixture.home_team} vs ${selectedFixture.away_team}: ${outcomeLabels[outcome]}`,
        probability: prediction.wdl[outcome],
        american_odds: odds,
      },
    ])
  }

  return (
    <main className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">World Cup Quant Desk</p>
          <h1>Scoreline probabilities, market edges, parlay stress tests.</h1>
          <p className="hero-copy">
            A local prediction lab for exact scores, moneylines, and simulation. No sportsbook execution. No guarantees.
          </p>
        </div>
        <div className="hero-metrics" aria-label="Model summary">
          <div>
            <Trophy size={18} />
            <span>{fixtures.length || '-'} fixtures</span>
          </div>
          <div>
            <Target size={18} />
            <span>{prediction ? prediction.confidence : 'loading'} confidence</span>
          </div>
          <div>
            <Activity size={18} />
            <span>{parlayLegs.length} parlay legs</span>
          </div>
          <div className={`sync-pill ${syncSummary.tone}`}>
            <RefreshCcw size={18} />
            <span>{syncSummary.label}</span>
          </div>
        </div>
      </section>

      <section className={`notice sync-notice ${syncSummary.tone}`}>
        <RefreshCcw size={18} />
        <span>{syncSummary.detail}</span>
      </section>

      {error && (
        <section className="notice error">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </section>
      )}

      <section className="workspace">
        <aside className="fixture-rail">
          <div className="rail-head">
            <h2>Games</h2>
            <RefreshCcw size={16} />
          </div>
          {loading && <p className="muted">Loading fixtures...</p>}
          {fixtureDateGroups.map((group) => {
            const isOpen = Boolean(openDateGroups[group.key])
            return (
              <div className="date-group" key={group.key}>
                <button
                  className="date-group-toggle"
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() => toggleDateGroup(group.key)}
                >
                  <span>{group.label}</span>
                  <small>{group.fixtures.length} games</small>
                  {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </button>
                {isOpen && (
                  <div className="date-group-games">
                    {group.fixtures.map((fixture) => (
                      <button
                        className={`fixture-button ${fixture.id === selectedId ? 'active' : ''}`}
                        key={fixture.id}
                        onClick={() => setSelectedId(fixture.id)}
                      >
                        <span>{fixture.home_team}</span>
                        <strong>vs</strong>
                        <span>{fixture.away_team}</span>
                        <small>{gameTimeLabel(fixture.kickoff)} / {fixture.venue}</small>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </aside>

        <section className="match-panel">
          {!selectedFixture || !prediction ? (
            <div className="empty">Select game to load prediction.</div>
          ) : (
            <>
              <div className="match-head">
                <div>
                  <p className="eyebrow">{selectedFixture.stage} / {kickoffLabel(selectedFixture.kickoff)}</p>
                  <h2>{selectedFixture.home_team} <span>vs</span> {selectedFixture.away_team}</h2>
                  {selectedFixture.status && <p className="muted">Status: {selectedFixture.status}{selectedFixture.score?.home !== null && selectedFixture.score?.home !== undefined ? ` / ${selectedFixture.score.home}-${selectedFixture.score.away}` : ''}</p>}
                </div>
                <div className={`confidence ${prediction.confidence}`}>{prediction.confidence}</div>
              </div>
              <div className="risk-badges" aria-label="Model risk flags">
                <span>{prediction.model_version}</span>
                <span className={`quality ${prediction.data_quality.level}`}>
                  {prediction.data_quality.level} data quality
                </span>
                {prediction.calibration.method !== 'none' && (
                  <span>market blend {(prediction.calibration.market_weight * 100).toFixed(0)}%</span>
                )}
                {prediction.risk_flags.length === 0 ? (
                  <span>no risk flags</span>
                ) : (
                  prediction.risk_flags.map((flag) => <span className="risk" key={flag}>{flag}</span>)
                )}
              </div>

              <div className="prob-row">
                {(['home', 'draw', 'away'] as const).map((outcome) => (
                  <div className="prob-tile" key={outcome}>
                    <span>{outcome === 'home' ? selectedFixture.home_team : outcome === 'away' ? selectedFixture.away_team : 'Draw'}</span>
                    <strong>{formatPercent(prediction.calibrated_wdl[outcome])}</strong>
                    {prediction.calibration.method !== 'none' && <small>{formatPercent(prediction.wdl[outcome])} raw model</small>}
                    {prediction.edges && (
                      <button onClick={() => addLeg(outcome)}>
                        <Plus size={14} /> odds {prediction.edges[outcome].american_odds}
                      </button>
                    )}
                  </div>
                ))}
              </div>

              <div className="split-grid">
                <section className="panel-block">
                  <h3><BarChart3 size={17} /> Top scorelines</h3>
                  {prediction.top_scores.map((score) => (
                    <div className="score-row" key={score.score}>
                      <span>{score.score}</span>
                      <meter value={score.probability} max={prediction.top_scores[0].probability}></meter>
                      <strong>{formatPercent(score.probability)}</strong>
                    </div>
                  ))}
                </section>

                <section className="panel-block">
                  <h3><Target size={17} /> Market edge</h3>
                  {edge ? (
                    <div className="edge-callout">
                      <span>Best positive edge</span>
                      <strong>{outcomeLabels[edge.outcome as keyof typeof outcomeLabels]}</strong>
                      <small>{formatPercent(edge.edge)} edge / ${edge.expectedValue.toFixed(2)} EV per $10</small>
                    </div>
                  ) : (
                    <p className="muted">No positive edge in current seed odds.</p>
                  )}
                  <p className="muted">Vig removed before edge calc. Correlation risk not included in v1.</p>
                </section>
              </div>

              <section className="panel-block stats-block">
                <h3>Team stat profiles</h3>
                <div className="stats-pair">
                  {[
                    [selectedFixture.home_team, homeStats],
                    [selectedFixture.away_team, awayStats],
                  ].map(([teamName, stats]) => (
                    <div className="stat-card" key={String(teamName)}>
                      <strong>{String(teamName)}</strong>
                      <small>{typeof stats === 'object' ? stats.source : ''}</small>
                      <span>{typeof stats === 'object' ? stats.matches : '0'} matches</span>
                      <span>{typeof stats === 'object' ? stats.record : '0-0-0'} record</span>
                      <span>{typeof stats === 'object' ? stats.points : '0 pts'}</span>
                      <span>{typeof stats === 'object' ? stats.xgPerMatch : '0.00'} xG/match</span>
                      <span>{typeof stats === 'object' ? stats.shotsPerMatch : '0.0'} shots/match</span>
                      <span>{typeof stats === 'object' ? stats.goalsPerMatch : '0.00'} goals/match</span>
                      <span>{typeof stats === 'object' ? stats.goalsAgainst : '0 GA'}</span>
                    </div>
                  ))}
                </div>
              </section>

              <section className="panel-block matrix-block">
                <h3>Exact score grid</h3>
                <div className="score-grid">
                  {matrixCells.map((cell) => (
                    <div className="score-cell" key={cell.score}>
                      <strong>{cell.score}</strong>
                      <span>{formatPercent(cell.probability)}</span>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}
        </section>

        <aside className="parlay-panel">
          <h2>Parlay Lab</h2>
          {parlayLegs.length === 0 ? (
            <p className="muted">Add moneyline legs from game probabilities.</p>
          ) : (
            <>
              {parlayLegs.map((leg, index) => (
                <div className="leg" key={`${leg.label}-${index}`}>
                  <span>{leg.label}</span>
                  <button onClick={() => setParlayLegs((legs) => legs.filter((_, legIndex) => legIndex !== index))}>Remove</button>
                </div>
              ))}
              <div className="parlay-total">
                <span>Combined probability</span>
                <strong>{formatPercent(parlay.combinedProbability)}</strong>
                <span>Decimal odds</span>
                <strong>{parlay.decimalOdds.toFixed(2)}</strong>
                <span>EV per $10</span>
                <strong className={parlay.expectedValuePer10 >= 0 ? 'positive' : 'negative'}>
                  ${parlay.expectedValuePer10.toFixed(2)}
                </strong>
              </div>
            </>
          )}
        </aside>
      </section>

      <section className="recommendations-panel">
        <div className="recommendations-head">
          <div>
            <p className="eyebrow">Recommended Bets</p>
            <h2>Positive edge only. No odds, no pick.</h2>
          </div>
          {recSummary && (
            <div className="rec-stats">
              <span>{recSummary.singleCount} singles</span>
              <span>{recSummary.parlayCount} parlays</span>
              <span>{recSummary.bestEdge} best edge</span>
            </div>
          )}
        </div>
        {recommendations ? (
          <>
            <p className="warning-copy">{recommendations.warning}</p>
            <div className="recommendations-grid">
              <section className="panel-block rec-list">
                <h3>Best single bets</h3>
                {recommendations.best_singles.length === 0 ? (
                  <p className="muted">No positive-EV bets found with current real odds.</p>
                ) : (
                  recommendations.best_singles.slice(0, 6).map((bet) => (
                    <div className="rec-row" key={`${bet.fixture_id}-${bet.selection}`}>
                      <div>
                        <strong>{bet.selection}</strong>
                        <span>{bet.match} / {bet.market}</span>
                        <small>{bet.source}{bet.last_updated ? ` / ${bet.last_updated}` : ''}</small>
                      </div>
                      <div>
                        <span>{formatPercent(bet.model_probability)} model</span>
                        <span>{formatPercent(bet.market_probability)} market</span>
                        <strong>{formatPercent(bet.edge)} edge</strong>
                        <small>${bet.expected_value_per_10.toFixed(2)} EV per $10 / {bet.american_odds}</small>
                      </div>
                    </div>
                  ))
                )}
              </section>

              <section className="panel-block rec-list">
                <h3>Parlay candidates</h3>
                {recommendations.parlay_candidates.length === 0 ? (
                  <p className="muted">Need 2+ positive-edge games from different fixtures.</p>
                ) : (
                  recommendations.parlay_candidates.map((candidate, index) => (
                    <div className="parlay-card" key={index}>
                      <strong>{formatPercent(candidate.combined_probability)} combined probability</strong>
                      <span>{candidate.decimal_odds.toFixed(2)} decimal odds</span>
                      <span>${candidate.expected_value_per_10.toFixed(2)} EV per $10</span>
                      {candidate.legs.map((leg) => (
                        <small key={`${leg.fixture_id}-${leg.selection}`}>{leg.selection} / {leg.match}</small>
                      ))}
                    </div>
                  ))
                )}
              </section>

              <section className="panel-block rec-list">
                <h3>Avoid / no edge</h3>
                {recommendations.avoid.slice(0, 8).map((item) => (
                  <div className="avoid-row" key={item.fixture_id}>
                    <strong>{item.match}</strong>
                    <span>{item.reason}</span>
                  </div>
                ))}
              </section>
            </div>
          </>
        ) : (
          <p className="muted">Loading recommendations...</p>
        )}
      </section>
    </main>
  )
}

export default App
