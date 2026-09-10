import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, API_BASE_URL } from './api'
import RailwayMap from './components/RailwayMap'
import type { Alert, EtaPrediction, LivePosition, RealtimeEvent, Station, Train, WeatherData } from './types'

type Data = { train: Train; live: LivePosition; route: Station[]; eta: EtaPrediction[] }
type Section = 'overview' | 'trains' | 'map' | 'alerts' | 'analytics' | 'settings'
type Theme = 'light' | 'dark' | 'system'
type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'stale' | 'error'

const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws')

const unavailableWeather: WeatherData = {
  temperature: null,
  feels_like: null,
  humidity: null,
  weather_condition: null,
  precipitation: null,
  wind_speed: null,
  visibility: null,
  weather_delay_risk: 'UNAVAILABLE',
  weather_last_updated: null,
  source: 'UNAVAILABLE',
  data_quality: 'UNAVAILABLE',
  observation_timestamp: null,
  available: false,
  message: 'Weather data unavailable',
}

function safeWeather(weather: WeatherData | undefined): WeatherData { return weather || unavailableWeather }

const navigation: { id: Section; label: string; icon: string }[] = [
  { id: 'overview', label: 'Overview', icon: 'OV' },
  { id: 'trains', label: 'Live Trains', icon: 'TR' },
  { id: 'map', label: 'Map', icon: 'MP' },
  { id: 'alerts', label: 'Alerts', icon: 'AL' },
  { id: 'analytics', label: 'Analytics', icon: 'AN' },
  { id: 'settings', label: 'Settings', icon: 'SE' },
]

function App() {
  const [trains, setTrains] = useState<Train[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [data, setData] = useState<Data | null>(null)
  const [section, setSection] = useState<Section>('overview')
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('dynamic-eta-theme') as Theme) || 'system')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected')
  const [lastUpdated, setLastUpdated] = useState('')
  const [now, setNow] = useState(() => Date.now())
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [toast, setToast] = useState<Alert | null>(null)

  useEffect(() => {
    const root = document.documentElement
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    root.dataset.theme = theme === 'system' ? (prefersDark ? 'dark' : 'light') : theme
    localStorage.setItem('dynamic-eta-theme', theme)
  }, [theme])

  useEffect(() => {
    api.trains()
      .then((items) => {
        setTrains(items)
        setSelectedId(items[0]?.train_id || '')
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedId) return
    setLoading(true)
    setError('')
    Promise.all([api.live(selectedId), api.route(selectedId), api.eta(selectedId)])
      .then(([live, route, eta]) => {
        const train = trains.find((item) => item.train_id === selectedId)
        if (train) setData({ train, live, route, eta })
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [selectedId, trains])

  useEffect(() => {
    api.alerts(selectedId ? `?train_id=${encodeURIComponent(selectedId)}` : '')
      .then(setAlerts)
      .catch(() => setAlerts([]))
  }, [selectedId])

  useEffect(() => {
    if (!selectedId) return
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    let disposed = false
    const connect = () => {
      if (disposed) return
      setConnectionStatus('connecting')
      socket = new WebSocket(`${WS_BASE_URL}/ws/trains/${selectedId}`)
      socket.onopen = () => setConnectionStatus('connected')
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as RealtimeEvent
          if (event.alerts?.length) {
            setAlerts((current) => [...event.alerts, ...current.filter((item) => !event.alerts.some((incoming) => incoming.id === item.id))])
            const notification = event.alerts.find((item) => item.severity === 'CRITICAL' || item.severity === 'WARNING')
            if (notification) {
              setToast(notification)
              window.setTimeout(() => setToast((current) => current?.id === notification.id ? null : current), 6000)
            }
          }
          setLastUpdated(event.timestamp)
          setConnectionStatus('connected')
          setData((current) => {
            if (!current) return current
            const nextStation = current.route.find((station) => station.name === event.next_station)
            const nextEta: EtaPrediction = {
              ...(current.eta[0] || { train_id: event.train_id, station_id: nextStation?.station_id || '', confidence: 0.8, model_version: 'demo-rf-v1', data_source: event.data_source }),
              station_id: nextStation?.station_id || current.eta[0]?.station_id || '',
              station_name: event.next_station,
              estimated_arrival: event.eta,
              minutes_remaining: Math.max(0, Math.round((new Date(event.eta).getTime() - Date.now()) / 60000)),
            }
            return { ...current, live: { ...current.live, latitude: event.latitude, longitude: event.longitude, speed_kmph: event.speed, recorded_at: event.timestamp, current_delay: event.current_delay, data_source: event.data_source, source: event.source, is_live: event.is_live, data_quality: event.data_quality, last_updated: event.last_updated, next_station: event.next_station, distance_to_next_station: event.distance_to_next_station, weather: event.weather || current.live.weather || unavailableWeather, eta: event.eta, eta_confidence: event.eta_confidence, predicted_delay: event.predicted_delay, confidence_level: event.confidence_level, prediction_source: event.prediction_source }, eta: [nextEta, ...current.eta.slice(1)] }
          })
        } catch {
          setConnectionStatus('error')
        }
      }
      socket.onerror = () => setConnectionStatus('error')
      socket.onclose = () => {
        if (!disposed) {
          setConnectionStatus('disconnected')
          reconnectTimer = window.setTimeout(connect, 1500)
        }
      }
    }
    connect()
    return () => {
      disposed = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [selectedId])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const nextEta = data?.eta[0]
  const progress = useMemo(() => {
    if (!data || !nextEta) return 0
    const total = data.eta[data.eta.length - 1]?.minutes_remaining || 1
    return Math.min(100, Math.max(4, Math.round((1 - nextEta.minutes_remaining / total) * 100)))
  }, [data, nextEta])

  const selectSection = (next: Section) => setSection(next)

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">D</div>
          <div><strong>Dynamic ETA</strong><span>Rail intelligence</span></div>
        </div>
        <nav aria-label="Primary navigation">
          <p className="nav-label">Workspace</p>
          {navigation.map((item) => (
            <button className={`nav-item ${section === item.id ? 'active' : ''}`} key={item.id} onClick={() => selectSection(item.id)}>
              <span className="nav-icon">{item.icon}</span><span>{item.label}</span>
              {item.id === 'alerts' && <b className="nav-count">{alerts.filter((alert) => !alert.acknowledged).length}</b>}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer"><span className={`connection-dot ${connectionStatus}`} /> <span>{data?.live.data_source === 'LIVE' ? 'LIVE source' : 'DEMO environment'}</span><small>Operational workspace</small></div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div><p className="eyebrow">OPERATIONS CONSOLE <span className="demo-badge">{data?.live.data_quality === 'STALE' ? 'STALE' : data?.live.is_live ? 'LIVE' : 'DEMO DATA'}</span></p><h1>{navigation.find((item) => item.id === section)?.label}</h1></div>
          <div className="topbar-actions">
            <div className="clock-panel"><span>{new Date(now).toLocaleDateString()}</span><strong>{new Date(now).toLocaleTimeString()}</strong></div>
            <label className="train-search"><span aria-hidden="true">⌕</span><input value={selectedId} onChange={(e) => setSelectedId(e.target.value)} list="train-options" placeholder="Search train ID" aria-label="Search train" /><datalist id="train-options">{trains.map((train) => <option key={train.train_id} value={train.train_id}>{train.number} {train.name}</option>)}</datalist></label>
            <select value={theme} onChange={(e) => setTheme(e.target.value as Theme)} aria-label="Color theme"><option value="system">System theme</option><option value="light">Light theme</option><option value="dark">Dark theme</option></select>
          </div>
        </header>

        {loading && <section className="state-card"><div className="spinner" />Loading DEMO railway data…</section>}
        {!loading && error && <section className="state-card error"><strong>Unable to load dashboard data</strong><p>{error}</p><small>Check that the backend is running at {import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'}.</small></section>}
        {!loading && !error && !trains.length && <section className="state-card"><strong>No trains available</strong><p>There are no DEMO trains to display yet.</p></section>}
        {!loading && !error && data && <DashboardContent section={section} data={data} alerts={alerts} onAlertsChange={setAlerts} progress={progress} onSectionChange={selectSection} connectionStatus={lastUpdated && now - new Date(lastUpdated).getTime() > 10000 ? 'stale' : connectionStatus} lastUpdated={lastUpdated} />}
        {toast && <button className={`alert-toast ${toast.severity.toLowerCase()}`} onClick={() => { setSection('alerts'); setToast(null) }}><span>{toast.severity === 'CRITICAL' ? '!' : 'i'}</span><div><strong>{toast.title}</strong><small>{toast.message}</small></div><b>×</b></button>}
        <footer>DEMO data only · Not live railway telemetry · Ready for future real-time integration</footer>
      </main>
      <nav className="mobile-nav" aria-label="Mobile navigation">{navigation.map((item) => <button className={section === item.id ? 'active' : ''} key={item.id} onClick={() => selectSection(item.id)}><span>{item.icon}</span>{item.label}</button>)}</nav>
    </div>
  )
}

function DashboardContent({ section, data, alerts, onAlertsChange, progress, onSectionChange, connectionStatus, lastUpdated }: { section: Section; data: Data; alerts: Alert[]; onAlertsChange: (alerts: Alert[]) => void; progress: number; onSectionChange: (section: Section) => void; connectionStatus: ConnectionStatus; lastUpdated: string }) {
  const nextEta = data.eta[0]
  const stats = <div className="stat-grid">
    <Metric label="Current speed" value={`${Math.round(data.live.speed_kmph)}`} unit="km/h" detail={`Updated ${connectionStatus === 'connected' ? 'automatically' : 'from last event'} · ${data.live.data_source}`} />
    <Metric label="Current delay" value={`${data.live.current_delay}`} unit="min" detail="Simulated operational delay" />
    <Metric label="AI predicted ETA" value={`${nextEta?.minutes_remaining ?? '—'}`} unit="min" detail={nextEta ? `To ${nextEta.station_name}` : 'No prediction'} />
    <Metric label="Confidence" value={nextEta ? `${Math.round(nextEta.confidence * 100)}` : '—'} unit="%" detail={nextEta?.model_version || 'Model unavailable'} />
    <Metric label="Predicted delay" value={`${data.live.predicted_delay}`} unit="min" detail={`${data.live.confidence_level} confidence`} />
  </div>

  if (section === 'alerts') return <AlertsPanel data={data} alerts={alerts} onAlertsChange={onAlertsChange} connectionStatus={connectionStatus} />
  if (section === 'analytics') return <AnalyticsPanel data={data} alerts={alerts} />
  if (section === 'settings') return <Placeholder title="Settings" text="Dashboard preferences are available from the theme control in the header." icon="SE" />
  if (section === 'trains') return <section className="content-stack"><TrainHero data={data} progress={progress} status={connectionStatus} onMap={() => onSectionChange('map')} /><section className="dashboard-grid"><EtaCard data={data} /><WeatherCard weather={data.live.weather} /></section>{stats}<RealtimeInfoPanel data={data} status={connectionStatus} lastUpdated={lastUpdated} /></section>

  return <section className="content-stack">
    <section className="welcome-row"><div><p className="eyebrow">NETWORK CONTROL · {new Date().toLocaleDateString(undefined, { weekday: 'long' })}</p><h2>Good morning, operator</h2><p className="muted">A live operational view of movement, prediction health, and service conditions.</p></div><button className="primary-button" onClick={() => onSectionChange('map')}><span className="button-glyph">↗</span> Open map</button></section>
    <TrainHero data={data} progress={progress} status={connectionStatus} onMap={() => onSectionChange('map')} />
    <section className="dashboard-grid"><EtaCard data={data} /><WeatherCard weather={data.live.weather} /></section>
    {section === 'map' ? <MapPanel data={data} /> : <section className="overview-grid"><section className="panel station-panel"><PanelTitle eyebrow="ROUTE STATUS" title="Station timeline" action={<button className="text-button" onClick={() => onSectionChange('map')}>View map →</button>} />{data.route.map((station, index) => <div className="timeline-row" key={station.station_id}><span className={`timeline-dot ${index === 0 ? 'complete' : index === 1 ? 'current' : ''}`} /><span className="timeline-copy"><strong>{station.name}</strong><small>{station.code} · {index === 0 ? 'Departed' : index === 1 ? 'Next stop' : 'Destination'}</small></span><b>{index === 0 ? '—' : data.eta[index - 1] ? `${data.eta[index - 1].minutes_remaining} min` : '—'}</b></div>)}</section><section className="panel insight-panel"><PanelTitle eyebrow="AI INSIGHT" title="Prediction health" /><div className="confidence-ring"><strong>{nextEta ? `${Math.round(nextEta.confidence * 100)}%` : '—'}</strong><span>confidence</span></div><p>Baseline model prediction for the next station, trained on synthetic DEMO history.</p><span className="demo-note">DEMO MODEL · {nextEta?.model_version || '—'}</span></section></section>}
    {stats}
    <RealtimeInfoPanel data={data} status={connectionStatus} lastUpdated={lastUpdated} />
    <ActivityStrip data={data} status={connectionStatus} lastUpdated={lastUpdated} />
  </section>
}

function StatusBadge({ data, status }: { data: Data; status: ConnectionStatus }) {
  const label = data.live.data_quality === 'STALE' ? 'STALE' : data.live.is_live ? 'LIVE' : data.live.data_quality === 'UNAVAILABLE' ? 'UNAVAILABLE' : 'DEMO DATA'
  return <span className={`status-badge ${label.toLowerCase().replace(' ', '-')}`}><i />{label}<small>{status === 'connected' ? 'streaming' : status}</small></span>
}

function TrainHero({ data, progress, status, onMap }: { data: Data; progress: number; status: ConnectionStatus; onMap: () => void }) {
  return <section className="train-hero panel"><div className="hero-top"><div className="hero-identity"><div className="train-emblem">{data.train.number.slice(-3)}</div><div><p className="eyebrow">SELECTED TRAIN · {data.train.data_source}</p><h2>{data.train.name}</h2><p className="hero-route">{data.train.number} <span>·</span> {data.train.origin} <b>→</b> {data.train.destination}</p></div></div><div className="hero-actions"><StatusBadge data={data} status={status} /><button className="icon-button" onClick={onMap} aria-label="Open map" title="Open map">↗</button></div></div><div className="hero-bottom"><div className="hero-eta"><span className="eyebrow">ESTIMATED ARRIVAL</span><strong>{data.eta[0] ? new Date(data.eta[0].estimated_arrival).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</strong><span>{data.eta[0]?.minutes_remaining ?? '—'} min to {data.eta[0]?.station_name || 'next station'}</span></div><div className="hero-stats"><HeroStat label="Speed" value={`${Math.round(data.live.speed_kmph)}`} unit="km/h" /><HeroStat label="Delay" value={`${data.live.current_delay}`} unit="min" /><HeroStat label="Next station" value={data.eta[0]?.station_name || '—'} /><HeroStat label="Updated" value={data.live.last_updated ? new Date(data.live.last_updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'} /></div></div><div className="progress-track"><span style={{ width: `${progress}%` }} /><b style={{ left: `${progress}%` }} /></div><div className="hero-progress-caption"><span>Origin <strong>{data.train.origin}</strong></span><span>{progress}% route progress</span><span>Destination <strong>{data.train.destination}</strong></span></div></section>
}

function HeroStat({ label, value, unit }: { label: string; value: string; unit?: string }) { return <div><span>{label}</span><strong>{value} <small>{unit}</small></strong></div> }

function EtaCard({ data }: { data: Data }) { const eta = data.eta[0]; return <section className="panel eta-card"><div className="card-heading"><div><p className="eyebrow">PREDICTION WINDOW</p><h3>Next arrival</h3></div><span className="soft-chip">{data.live.prediction_source}</span></div><div className="eta-value">{eta ? new Date(eta.estimated_arrival).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</div><p className="eta-subtitle">{eta?.minutes_remaining ?? '—'} minutes · {eta?.station_name || 'Awaiting station'}</p><div className="eta-details"><span><small>Predicted delay</small><b>{data.live.predicted_delay} min</b></span><span><small>Confidence</small><b>{data.live.confidence_level} · {Math.round((data.live.eta_confidence || 0) * 100)}%</b></span><span><small>Last updated</small><b>{data.live.last_updated ? new Date(data.live.last_updated).toLocaleTimeString() : '—'}</b></span></div></section> }

function WeatherCard({ weather: rawWeather }: { weather: LivePosition['weather'] | undefined }) { const weather = safeWeather(rawWeather); const state = weather.available ? 'LIVE' : weather.source === 'DEMO' ? 'DEMO' : 'UNAVAILABLE'; return <section className="panel weather-card"><div className="card-heading"><div><p className="eyebrow">ATMOSPHERIC CONDITIONS</p><h3>Weather at train</h3></div><span className={`weather-state ${state.toLowerCase()}`}><i />{state}</span></div>{weather.available ? <><div className="weather-main"><strong>{weather.temperature ?? '—'}°</strong><span>{weather.weather_condition || 'Observed conditions'}<small>Feels like {weather.feels_like ?? '—'}°</small></span></div><div className="weather-details"><span>Humidity <b>{weather.humidity ?? '—'}%</b></span><span>Wind <b>{weather.wind_speed ?? '—'} m/s</b></span><span>Visibility <b>{weather.visibility ? `${(weather.visibility / 1000).toFixed(1)} km` : '—'}</b></span></div></> : <div className="weather-unavailable"><strong>{weather.message}</strong><span>No conditions are being inferred or simulated.</span></div>}<small className="source-line">Source · {weather.source}</small></section> }

function ActivityStrip({ data, status, lastUpdated }: { data: Data; status: ConnectionStatus; lastUpdated: string }) { return <section className="activity-strip"><div><i className={status === 'connected' ? 'pulse' : ''} /><span>Telemetry stream</span><b>{status === 'connected' ? 'Connected' : status}</b></div><div><i className="pulse" /><span>ETA engine</span><b>Updated {lastUpdated ? new Date(lastUpdated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'waiting'}</b></div><div><i className={data.live.weather.available ? 'pulse' : ''} /><span>Weather</span><b>{data.live.weather.available ? 'Observed' : 'Unavailable'}</b></div></section> }

function AlertsPanel({ data, alerts, onAlertsChange, connectionStatus }: { data: Data; alerts: Alert[]; onAlertsChange: (alerts: Alert[]) => void; connectionStatus: ConnectionStatus }) { const visibleAlerts = alerts.length ? alerts : [{ id: 'local-status', train_id: data.train.train_id, type: data.live.data_quality === 'STALE' ? 'DATA_STALE' : 'SYSTEM_STATUS', severity: data.live.data_quality === 'STALE' ? 'WARNING' : 'INFO', title: data.live.data_quality === 'STALE' ? 'Telemetry is stale' : 'Demo service operating normally', message: data.live.data_quality === 'STALE' ? 'Last known position is being displayed.' : 'This train is using clearly labelled DEMO telemetry.', created_at: new Date().toISOString(), acknowledged: false, source: data.train.data_source, data_quality: data.live.data_quality, metadata: {} } as Alert]; const acknowledge = (id: string) => { api.acknowledgeAlert(id).then((updated) => onAlertsChange(alerts.map((item) => item.id === id ? updated : item))).catch(() => undefined) }; return <section className="content-stack"><section className="section-intro"><p className="eyebrow">OPERATIONS SIGNALS</p><h2>Alerts <span className="section-count">{alerts.filter((item) => !item.acknowledged).length} active</span></h2><p className="muted">Prioritized events from the selected train and data services.</p></section><div className="alert-filters"><span>Selected train · {data.train.number}</span><span>Stream · {connectionStatus}</span><button onClick={() => onAlertsChange(alerts.filter((item) => item.acknowledged))}>Show acknowledged</button></div><section className="alert-list">{visibleAlerts.map((alert) => <article className={`alert-item ${alert.severity.toLowerCase()}`} key={alert.id}><span className="alert-icon">{alert.severity === 'CRITICAL' ? '!' : alert.severity === 'WARNING' ? '!' : 'i'}</span><div><div className="alert-title-row"><strong>{alert.title}</strong><span>{alert.type}</span></div><p>{alert.message}</p><small>{new Date(alert.created_at).toLocaleTimeString()} · {alert.source}</small></div>{!alert.acknowledged && alert.id !== 'local-status' && <button className="ack-button" onClick={() => acknowledge(alert.id)}>Acknowledge</button>}</article>)}</section></section> }

function AnalyticsPanel({ data, alerts }: { data: Data; alerts: Alert[] }) { const confidence = Math.round((data.live.eta_confidence || 0) * 100); const critical = alerts.filter((item) => item.severity === 'CRITICAL' && !item.acknowledged).length; const warning = alerts.filter((item) => item.severity === 'WARNING' && !item.acknowledged).length; return <section className="content-stack"><section className="section-intro"><p className="eyebrow">CONTROL ROOM METRICS · {data.train.data_source}</p><h2>Analytics</h2><p className="muted">Current operational performance for the selected train. Metrics retain their source and quality labels.</p></section><section className="analytics-kpis"><div><span>Active trains</span><b>1</b><small>{data.train.data_source} fleet</small></div><div><span>Delayed trains</span><b>{data.live.current_delay > 0 ? 1 : 0}</b><small>{data.live.current_delay > 0 ? 'Needs attention' : 'On time'}</small></div><div><span>Active alerts</span><b>{alerts.filter((item) => !item.acknowledged).length}</b><small>{critical} critical · {warning} warning</small></div><div><span>Data freshness</span><b>{data.live.data_quality}</b><small>{data.live.last_updated ? new Date(data.live.last_updated).toLocaleTimeString() : 'Unknown'}</small></div></section><section className="analytics-grid"><article className="analytics-card"><span>Current delay</span><strong>{data.live.current_delay}<small> min</small></strong><div className="spark-bars"><i /><i /><i /><i /><i /><i className="active" /></div><small>DEMO-derived operating signal</small></article><article className="analytics-card"><span>Prediction confidence</span><strong>{confidence}<small>%</small></strong><div className="confidence-bar"><i style={{ width: `${confidence}%` }} /></div><small>{data.live.confidence_level} confidence · {data.live.prediction_source}</small></article><article className="analytics-card wide"><span>Selected train performance</span><div className="route-analytics"><div><b>{Math.round(data.live.speed_kmph)}</b><small>km/h current speed</small></div><div><b>{data.live.predicted_delay}</b><small>minutes predicted delay</small></div><div><b>{data.eta[0]?.minutes_remaining ?? '—'}</b><small>minutes to arrival</small></div><div><b>{data.live.distance_to_next_station ?? '—'}</b><small>distance remaining</small></div></div></article></section></section> }

function MapPanel({ data }: { data: Data }) {
  return <section className="map-layout"><section className="panel map-panel"><PanelTitle eyebrow={`NETWORK VIEW · ${data.live.data_source}`} title="Railway map" action={<span className="map-help">Scroll to zoom · drag to explore</span>} /><div className="scene-wrap"><RailwayMap stations={data.route} live={data.live} /></div></section><section className="panel map-summary"><PanelTitle eyebrow="TRAIN DETAILS" title={data.train.name} /><div className="detail-list"><span>Train number <b>{data.train.number}</b></span><span>Current speed <b>{Math.round(data.live.speed_kmph)} km/h</b></span><span>Current delay <b>{data.live.current_delay} min</b></span><span>Next station <b>{data.eta[0]?.station_name || '—'}</b></span><span>ETA <b>{data.eta[0] ? new Date(data.eta[0].estimated_arrival).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</b></span></div><span className="demo-note">{data.live.data_source === 'DEMO' ? 'DEMO COORDINATES · NOT LIVE GPS' : 'AUTHORIZED LIVE POSITION'}</span></section></section>
}

function RealtimeInfoPanel({ data, status, lastUpdated }: { data: Data; status: ConnectionStatus; lastUpdated: string }) {
  const weather = safeWeather(data.live.weather)
  const statusLabel = data.live.data_quality === 'STALE' ? 'STALE' : status === 'connected' ? 'CONNECTED' : status.toUpperCase()
  const weatherStatus = weather.available ? 'LIVE' : weather.source === 'DEMO' ? 'DEMO' : 'UNAVAILABLE'
  const weatherValue = weather.available ? `${weather.weather_condition || 'Observed'} · ${weather.temperature ?? '—'}°C` : weather.message
  return <section className="panel realtime-panel"><PanelTitle eyebrow="REAL-TIME TRAIN INFORMATION" title={data.train.number} action={<span className={`connection-status ${status}`}><i />{statusLabel}</span>} /><div className="realtime-grid"><span>Current position <b>{data.live.latitude.toFixed(4)}, {data.live.longitude.toFixed(4)}</b></span><span>Current speed <b>{Math.round(data.live.speed_kmph)} km/h</b></span><span>Current delay <b>{data.live.current_delay} min</b></span><span>Predicted delay <b>{data.live.predicted_delay} min</b></span><span>Next station <b>{data.eta[0]?.station_name || '—'}</b></span><span>ETA <b>{data.eta[0] ? new Date(data.eta[0].estimated_arrival).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</b></span><span>Confidence <b>{data.live.confidence_level} · {Math.round((data.live.eta_confidence || 0) * 100)}%</b></span><span>Last updated <b>{lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : 'Waiting for event'}</b></span><span>Data source <b>{data.live.is_live ? 'LIVE' : data.live.data_quality === 'STALE' ? 'STALE' : data.live.data_source === 'DEMO' ? 'DEMO' : 'UNAVAILABLE'}</b></span><span>Weather <b>{weatherStatus} · {weatherValue}</b></span><span>Data quality <b>{data.live.data_quality}</b></span></div></section>
}

function Metric({ label, value, unit, detail }: { label: string; value: string; unit: string; detail: string }) {
  return <article className="metric-card"><span>{label}</span><strong>{value} <small>{unit}</small></strong><p>{detail}</p></article>
}

function PanelTitle({ eyebrow, title, action }: { eyebrow: string; title: string; action?: ReactNode }) {
  return <div className="panel-title"><div><p className="eyebrow">{eyebrow}</p><h3>{title}</h3></div>{action}</div>
}

function Placeholder({ title, text, icon }: { title: string; text: string; icon: string }) {
  return <section className="placeholder panel"><div className="placeholder-icon">{icon}</div><h2>{title}</h2><p>{text}</p><span className="demo-note">Available in a future operational release</span></section>
}

export default App
