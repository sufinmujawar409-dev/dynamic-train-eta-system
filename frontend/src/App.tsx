import {
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { api, API_BASE_URL } from './api'
import RailwayMap from './components/RailwayMap'

import type {
  Alert,
  EtaPrediction,
  LivePosition,
  RealtimeEvent,
  Station,
  Train,
  WeatherData,
} from './types'

type Data = {
  train: Train
  live: LivePosition
  route: Station[]
  eta: EtaPrediction[]
}

type Section =
  | 'overview'
  | 'trains'
  | 'map'
  | 'alerts'
  | 'analytics'
  | 'settings'

type Theme =
  | 'light'
  | 'dark'
  | 'system'

type Settings = {
  notifications: boolean
  delayAlerts: boolean
  etaAlerts: boolean
  criticalAlerts: boolean
  liveTracking: boolean
  autoRefresh: boolean
  autoEta: boolean
  refreshInterval: number
  showStations: boolean
  showTrainRoute: boolean
  showTrainPosition: boolean
  aiPrediction: boolean
  predictionConfidence: boolean
}

const defaultSettings: Settings = {
  notifications: true,
  delayAlerts: true,
  etaAlerts: true,
  criticalAlerts: true,
  liveTracking: true,
  autoRefresh: true,
  autoEta: true,
  refreshInterval: 10,
  showStations: true,
  showTrainRoute: true,
  showTrainPosition: true,
  aiPrediction: true,
  predictionConfidence: true,
}

const SETTINGS_API = `${API_BASE_URL}/api/settings`

async function fetchSettings(): Promise<Settings> {
  const response = await fetch(SETTINGS_API)

  if (!response.ok) {
    throw new Error('Failed to load settings')
  }

  return response.json() as Promise<Settings>
}

async function saveSettings(
  settings: Settings,
): Promise<Settings> {
  const response = await fetch(SETTINGS_API, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(settings),
  })

  if (!response.ok) {
    throw new Error('Failed to save settings')
  }

  return response.json() as Promise<Settings>
}

type ConnectionStatus =
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'stale'
  | 'error'

const WS_BASE_URL = API_BASE_URL
  .replace(/^https:/, 'wss:')
  .replace(/^http:/, 'ws:')

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

function safeWeather(
  weather: WeatherData | undefined,
): WeatherData {
  return weather ?? unavailableWeather
}

const navigation: {
  id: Section
  label: string
  icon: string
}[] = [
  {
    id: 'overview',
    label: 'Overview',
    icon: 'OV',
  },
  {
    id: 'trains',
    label: 'Live Trains',
    icon: 'TR',
  },
  {
    id: 'map',
    label: 'Map',
    icon: 'MP',
  },
  {
    id: 'alerts',
    label: 'Alerts',
    icon: 'AL',
  },
  {
    id: 'analytics',
    label: 'Analytics',
    icon: 'AN',
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: 'SE',
  },
]

function App() {
  const [trains, setTrains] =
    useState<Train[]>([])

  const [selectedId, setSelectedId] =
    useState('')

  const [searchValue, setSearchValue] =
    useState('')

  const [data, setData] =
    useState<Data | null>(null)

  const [section, setSection] =
    useState<Section>('overview')

  /*
   * THEME
   */
  const [theme, setTheme] =
    useState<Theme>(() => {
      const saved =
        localStorage.getItem(
          'dynamic-eta-theme',
        )

      if (
        saved === 'light' ||
        saved === 'dark' ||
        saved === 'system'
      ) {
        return saved
      }

      return 'system'
    })

  const [fleetLoading, setFleetLoading] =
    useState(true)

  const [trainLoading, setTrainLoading] =
    useState(false)

  const [error, setError] =
    useState('')

  const [
    connectionStatus,
    setConnectionStatus,
  ] = useState<ConnectionStatus>(
    'disconnected',
  )

  const [lastUpdated, setLastUpdated] =
    useState('')

  const [now, setNow] =
    useState(() => Date.now())

  const [settings, setSettings] =
    useState<Settings>(() => {
      try {
        const saved =
          localStorage.getItem(
            'dynamic-eta-settings',
          )

        if (!saved) {
          return defaultSettings
        }

        return {
          ...defaultSettings,
          ...(JSON.parse(saved) as Partial<Settings>),
        }
      } catch {
        return defaultSettings
      }
    })

  const updateSetting = <K extends keyof Settings>(
    key: K,
    value: Settings[K],
  ) => {
    setSettings((current) => {
      const nextSettings: Settings = {
        ...current,
        [key]: value,
      }

      void saveSettings(nextSettings).catch((error: Error) => {
        console.error('Unable to save settings:', error)
      })

      return nextSettings
    })
  }

  useEffect(() => {
    let cancelled = false

    async function loadSettings() {
      try {
        const serverSettings = await fetchSettings()

        if (!cancelled) {
          setSettings({
            ...defaultSettings,
            ...serverSettings,
          })
        }
      } catch (error) {
        console.warn(
          'Backend settings unavailable; using local settings.',
          error,
        )
      }
    }

    void loadSettings()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    localStorage.setItem(
      'dynamic-eta-settings',
      JSON.stringify(settings),
    )
  }, [settings])

  const [alerts, setAlerts] =
    useState<Alert[]>([])

  const [toast, setToast] =
    useState<Alert | null>(null)

  /*
   * THEME EFFECT
   */
  useEffect(() => {
    const root =
      document.documentElement

    const mediaQuery =
      window.matchMedia(
        '(prefers-color-scheme: dark)',
      )

    const applyTheme = () => {
      root.dataset.theme =
        theme === 'system'
          ? mediaQuery.matches
            ? 'dark'
            : 'light'
          : theme
    }

    applyTheme()

    localStorage.setItem(
      'dynamic-eta-theme',
      theme,
    )

    if (theme === 'system') {
      mediaQuery.addEventListener(
        'change',
        applyTheme,
      )

      return () => {
        mediaQuery.removeEventListener(
          'change',
          applyTheme,
        )
      }
    }

    return undefined
  }, [theme])

  /*
   * LOAD TRAIN FLEET
   */
  useEffect(() => {
    let cancelled = false

    setFleetLoading(true)
    setError('')

    api
      .trains()
      .then((items) => {
        if (cancelled) return

        setTrains(items)

        if (items.length > 0) {
          const firstId =
            items[0].train_id

          setSelectedId((current) => {
            const valid =
              items.some(
                (item) =>
                  item.train_id ===
                  current,
              )

            return valid
              ? current
              : firstId
          })

          setSearchValue((current) => {
            const valid =
              items.some(
                (item) =>
                  item.train_id ===
                  current,
              )

            return valid
              ? current
              : firstId
          })
        } else {
          setSelectedId('')
          setSearchValue('')
          setData(null)
        }
      })
      .catch((e: Error) => {
        if (cancelled) return

        setError(
          e.message ||
            'Unable to load trains',
        )
      })
      .finally(() => {
        if (!cancelled) {
          setFleetLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  /*
   * LOAD SELECTED TRAIN DATA
   */
  useEffect(() => {
    if (!selectedId) {
      setData(null)
      return
    }

    const selectedTrain =
      trains.find(
        (train) =>
          train.train_id ===
          selectedId,
      )

    if (!selectedTrain) {
      return
    }

    let cancelled = false

    setTrainLoading(true)
    setError('')

    setConnectionStatus(
      'connecting',
    )

    setData(null)

    Promise.all([
      api.live(selectedId),
      api.route(selectedId),
      api.eta(selectedId),
    ])
      .then(
        ([live, route, eta]) => {
          if (cancelled) return

          setData({
            train: selectedTrain,
            live,
            route,
            eta,
          })

          setLastUpdated(
            live.last_updated ||
              live.recorded_at ||
              '',
          )

          setSearchValue(
            selectedId,
          )
        },
      )
      .catch((e: Error) => {
        if (cancelled) return

        setError(
          e.message ||
            'Unable to load train data',
        )

        setConnectionStatus(
          'error',
        )
      })
      .finally(() => {
        if (!cancelled) {
          setTrainLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [selectedId, trains])

  /*
   * LOAD ALERTS
   */
  useEffect(() => {
    let cancelled = false

    if (!selectedId) {
      setAlerts([])
      return
    }

    api
      .alerts(
        `?train_id=${encodeURIComponent(
          selectedId,
        )}`,
      )
      .then((items) => {
        if (!cancelled) {
          setAlerts(items)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAlerts([])
        }
      })

    return () => {
      cancelled = true
    }
  }, [selectedId])

  /*
   * REALTIME WEBSOCKET
   */
  useEffect(() => {
    if (!selectedId) return

    let socket: WebSocket | null = null

    let reconnectTimer:
      | number
      | undefined

    let disposed = false

    const connect = () => {
      if (disposed) return

      setConnectionStatus(
        'connecting',
      )

      try {
        const trainId =
          encodeURIComponent(
            selectedId,
          )

        socket = new WebSocket(
          `${WS_BASE_URL}/ws/trains/${trainId}`,
        )
      } catch {
        setConnectionStatus(
          'error',
        )

        return
      }

      socket.onopen = () => {
        if (disposed) return

        setConnectionStatus(
          'connected',
        )
      }

      socket.onmessage = (
        message,
      ) => {
        if (disposed) return

        try {
          const event =
            JSON.parse(
              message.data,
            ) as RealtimeEvent

          /*
           * REALTIME ALERTS
           */
          if (
            event.alerts &&
            event.alerts.length > 0
          ) {
            setAlerts(
              (current) => {
                const incomingIds =
                  new Set(
                    event.alerts!.map(
                      (item) =>
                        item.id,
                    ),
                  )

                return [
                  ...event.alerts!,
                  ...current.filter(
                    (item) =>
                      !incomingIds.has(
                        item.id,
                      ),
                  ),
                ]
              },
            )

            const notification =
              event.alerts.find(
                (item) =>
                  item.severity ===
                    'CRITICAL' ||
                  item.severity ===
                    'WARNING',
              )

            if (notification) {
              setToast(notification)

              window.setTimeout(
                () => {
                  setToast(
                    (current) =>
                      current?.id ===
                      notification.id
                        ? null
                        : current,
                  )
                },
                6000,
              )
            }
          }

          /*
           * UPDATE STREAM STATUS
           */
          if (event.timestamp) {
            setLastUpdated(
              event.timestamp,
            )
          }

          setConnectionStatus(
            'connected',
          )

          /*
           * UPDATE SELECTED TRAIN
           */
          setData((current) => {
            if (!current) {
              return current
            }

            const nextStation =
              current.route.find(
                (station) =>
                  station.name ===
                  event.next_station,
              )

            const previousEta =
              current.eta[0]

            const eventEtaTime =
              event.eta
                ? new Date(
                    event.eta,
                  ).getTime()
                : NaN

            const minutesRemaining =
              Number.isFinite(
                eventEtaTime,
              )
                ? Math.max(
                    0,
                    Math.round(
                      (eventEtaTime -
                        Date.now()) /
                        60000,
                    ),
                  )
                : previousEta
                    ?.minutes_remaining ??
                  0

            const nextEta: EtaPrediction =
              {
                ...(previousEta || {
                  train_id:
                    event.train_id,

                  station_id:
                    nextStation?.station_id ||
                    '',

                  station_name:
                    event.next_station,

                  estimated_arrival:
                    event.eta,

                  minutes_remaining:
                    minutesRemaining,

                  confidence:
                    event.eta_confidence ??
                    0,

                  model_version:
                    'ETA-engine',

                  data_source:
                    event.data_source,
                }),

                train_id:
                  event.train_id,

                station_id:
                  nextStation?.station_id ||
                  previousEta?.station_id ||
                  '',

                station_name:
                  event.next_station,

                estimated_arrival:
                  event.eta,

                minutes_remaining:
                  minutesRemaining,

                confidence:
                  event.eta_confidence ??
                  previousEta?.confidence ??
                  0,

                data_source:
                  event.data_source,
              }

            return {
              ...current,

              live: {
                ...current.live,

                latitude:
                  event.latitude,

                longitude:
                  event.longitude,

                speed_kmph:
                  event.speed,

                recorded_at:
                  event.timestamp,

                current_delay:
                  event.current_delay,

                data_source:
                  event.data_source,

                source:
                  event.source,

                is_live:
                  event.is_live,

                data_quality:
                  event.data_quality,

                last_updated:
                  event.last_updated,

                next_station:
                  event.next_station,

                distance_to_next_station:
                  event.distance_to_next_station,

                weather:
                  event.weather ||
                  current.live.weather ||
                  unavailableWeather,

                eta: event.eta,

                eta_confidence:
                  event.eta_confidence,

                predicted_delay:
                  event.predicted_delay,

                confidence_level:
                  event.confidence_level,

                prediction_source:
                  event.prediction_source,
              },

              eta: [
                nextEta,
                ...current.eta.slice(
                  1,
                ),
              ],
            }
          })
        } catch {
          setConnectionStatus(
            'error',
          )
        }
      }

      socket.onerror = () => {
        if (!disposed) {
          setConnectionStatus(
            'error',
          )
        }
      }

      socket.onclose = () => {
        if (disposed) return

        setConnectionStatus(
          'disconnected',
        )

        reconnectTimer =
          window.setTimeout(
            connect,
            2000,
          )
      }
    }

    connect()

    return () => {
      disposed = true

      if (
        reconnectTimer !==
        undefined
      ) {
        window.clearTimeout(
          reconnectTimer,
        )
      }

      socket?.close()
      socket = null
    }
  }, [selectedId])

  /*
   * CLOCK
   */
  useEffect(() => {
    const timer =
      window.setInterval(() => {
        setNow(Date.now())
      }, 1000)

    return () =>
      window.clearInterval(timer)
  }, [])

  /*
   * ROUTE PROGRESS
   */
  const nextEta = data?.eta[0]

  const progress = useMemo(() => {
    if (!data) return 0

    const distanceToNextStation =
      data.live
        .distance_to_next_station ??
      0

    if (
      data.live.data_source ===
        'LIVE' &&
      distanceToNextStation > 0
    ) {
      const routeDistance =
        data.route.length > 1
          ? data.route.length - 1
          : 1

      return Math.min(
        100,
        Math.max(
          4,
          Math.round(
            ((routeDistance - 1) /
              routeDistance) *
              100,
          ),
        ),
      )
    }

    if (
      data.eta.length <= 1 ||
      !nextEta
    ) {
      return 8
    }

    const total =
      data.eta.reduce(
        (sum, item) =>
          sum +
          Math.max(
            0,
            item.minutes_remaining,
          ),
        0,
      )

    if (total <= 0) {
      return 95
    }

    const remaining =
      Math.max(
        0,
        nextEta.minutes_remaining,
      )

    return Math.min(
      100,
      Math.max(
        4,
        Math.round(
          (1 -
            remaining /
              total) *
            100,
        ),
      ),
    )
  }, [data, nextEta])

  /*
   * SECTION
   */
  const selectSection = (
    next: Section,
  ) => {
    setSection(next)
  }

  /*
   * SELECT TRAIN
   */
  const selectTrain = (
    trainId: string,
  ) => {
    const exists = trains.some(
      (train) =>
        train.train_id ===
        trainId,
    )

    if (!exists) return

    setSelectedId(trainId)
    setSearchValue(trainId)
    setSection('trains')
  }

  /*
   * SEARCH TRAIN
   */
  const handleTrainSearch = (
    value: string,
  ) => {
    setSearchValue(value)

    const exactTrain =
      trains.find(
        (train) =>
          train.train_id
            .toLowerCase() ===
          value
            .trim()
            .toLowerCase(),
      )

    if (exactTrain) {
      setSelectedId(
        exactTrain.train_id,
      )

      setSearchValue(
        exactTrain.train_id,
      )

      setSection('trains')
    }
  }

  const unreadAlerts =
    alerts.filter(
      (alert) =>
        !alert.acknowledged,
    ).length

  const displayLoading =
    fleetLoading || trainLoading

  /*
   * UI
   */
  return (
    <div className="app-shell">

      <aside className="sidebar">

        <div className="brand">
          <div className="brand-mark">
            D
          </div>

          <div>
            <strong>
              Dynamic ETA
            </strong>

            <span>
              Rail intelligence
            </span>
          </div>
        </div>

        <nav aria-label="Primary navigation">
          <p className="nav-label">
            Workspace
          </p>

          {navigation.map(
            (item) => (
              <button
                className={`nav-item ${
                  section === item.id
                    ? 'active'
                    : ''
                }`}
                key={item.id}
                onClick={() =>
                  selectSection(
                    item.id,
                  )
                }
                type="button"
              >
                <span className="nav-icon">
                  {item.icon}
                </span>

                <span>
                  {item.label}
                </span>

                {item.id ===
                  'alerts' &&
                  unreadAlerts >
                    0 && (
                    <b className="nav-count">
                      {unreadAlerts}
                    </b>
                  )}
              </button>
            ),
          )}
        </nav>

        <div className="sidebar-footer">
          <span
            className={`connection-dot ${connectionStatus}`}
          />

          <span>
            {data?.live.data_source ===
            'LIVE'
              ? 'LIVE source'
              : 'DEMO environment'}
          </span>

          <small>
            Operational workspace
          </small>
        </div>
      </aside>

      <main className="main-content">

        <header className="topbar">

          <div>
            <p className="eyebrow">
              OPERATIONS CONSOLE{' '}
              <span className="demo-badge">
                {data?.live
                  .data_quality ===
                'STALE'
                  ? 'STALE'
                  : data?.live
                        .is_live
                    ? 'LIVE'
                    : 'DEMO DATA'}
              </span>
            </p>

            <h1>
              {
                navigation.find(
                  (item) =>
                    item.id ===
                    section,
                )?.label
              }
            </h1>
          </div>

          <div className="topbar-actions">

            <div className="clock-panel">
              <span>
                {new Date(
                  now,
                ).toLocaleDateString()}
              </span>

              <strong>
                {new Date(
                  now,
                ).toLocaleTimeString()}
              </strong>
            </div>

            <label className="train-search">
              <span aria-hidden="true">
                ⌕
              </span>

              <input
                value={searchValue}
                onChange={(e) =>
                  handleTrainSearch(
                    e.target.value,
                  )
                }
                list="train-options"
                placeholder="Search train ID"
                aria-label="Search train"
              />

              <datalist id="train-options">
                {trains.map(
                  (train) => (
                    <option
                      key={
                        train.train_id
                      }
                      value={
                        train.train_id
                      }
                      label={`${train.number} ${train.name}`}
                    />
                  ),
                )}
              </datalist>
            </label>

            <select
              value={theme}
              onChange={(e) =>
                setTheme(
                  e.target
                    .value as Theme,
                )
              }
              aria-label="Color theme"
            >
              <option value="system">
                System theme
              </option>

              <option value="light">
                Light theme
              </option>

              <option value="dark">
                Dark theme
              </option>
            </select>

          </div>
        </header>

        {displayLoading && (
          <section className="state-card">
            <div className="spinner" />

            Loading railway data…
          </section>
        )}

        {!displayLoading &&
          error && (
            <section className="state-card error">

              <strong>
                Unable to load dashboard
                data
              </strong>

              <p>
                {error}
              </p>

              <small>
                Check that the backend
                is running at{' '}
                {import.meta.env
                  .VITE_API_BASE_URL ||
                  'http://127.0.0.1:8000'}
              </small>

            </section>
          )}

        {!displayLoading &&
          !error &&
          !trains.length && (
            <section className="state-card">

              <strong>
                No trains available
              </strong>

              <p>
                There are currently
                no trains available
                from the configured
                data source.
              </p>

            </section>
          )}

        {!displayLoading &&
          !error &&
          data && (
            <DashboardContent
              section={section}
              data={data}
              trains={trains}
              alerts={alerts}
              onAlertsChange={
                setAlerts
              }
              progress={progress}
              onSectionChange={
                selectSection
              }
              onTrainSelect={
                selectTrain
              }
              connectionStatus={
                lastUpdated &&
                Number.isFinite(
                  new Date(
                    lastUpdated,
                  ).getTime(),
                ) &&
                now -
                  new Date(
                    lastUpdated,
                  ).getTime() >
                  10000
                  ? 'stale'
                  : connectionStatus
              }
              lastUpdated={
                lastUpdated
              }
              theme={theme}
              onThemeChange={
                setTheme
              }
              settings={settings}
              onSettingChange={updateSetting}
            />
          )}

        {toast && (
          <button
            className={`alert-toast ${toast.severity.toLowerCase()}`}
            onClick={() => {
              setSection('alerts')
              setToast(null)
            }}
            type="button"
          >
            <span>
              {toast.severity ===
              'CRITICAL'
                ? '!'
                : 'i'}
            </span>

            <div>
              <strong>
                {toast.title}
              </strong>

              <small>
                {toast.message}
              </small>
            </div>

            <b>
              ×
            </b>
          </button>
        )}

        <footer>
          Source-aware railway data ·
          DEMO and authorized LIVE
          feeds are clearly labelled
        </footer>

      </main>

      <nav
        className="mobile-nav"
        aria-label="Mobile navigation"
      >
        {navigation.map(
          (item) => (
            <button
              className={
                section === item.id
                  ? 'active'
                  : ''
              }
              key={item.id}
              onClick={() =>
                selectSection(
                  item.id,
                )
              }
              type="button"
            >
              <span>
                {item.icon}
              </span>

              {item.label}
            </button>
          ),
        )}
      </nav>

    </div>
  )
}

/*
 * DASHBOARD CONTENT
 */
function DashboardContent({
  section,
  data,
  trains,
  alerts,
  onAlertsChange,
  progress,
  onSectionChange,
  onTrainSelect,
  connectionStatus,
  lastUpdated,
  theme,
  onThemeChange,
  settings,
  onSettingChange,
}: {
  section: Section
  data: Data
  trains: Train[]
  alerts: Alert[]
  onAlertsChange: (
    alerts: Alert[],
  ) => void
  progress: number
  onSectionChange: (
    section: Section,
  ) => void
  onTrainSelect: (
    trainId: string,
  ) => void
  connectionStatus: ConnectionStatus
  lastUpdated: string
  theme: Theme
  onThemeChange: (
    theme: Theme,
  ) => void
  settings: Settings
  onSettingChange: <K extends keyof Settings>(
    key: K,
    value: Settings[K],
  ) => void
}) {
  const nextEta = data.eta[0]

  const stats = (
    <div className="stat-grid">

      <Metric
        label="Current speed"
        value={`${Math.round(
          data.live.speed_kmph,
        )}`}
        unit="km/h"
        detail={`Updated ${
          connectionStatus ===
          'connected'
            ? 'automatically'
            : 'from last event'
        } · ${
          data.live.data_source
        }`}
      />

      <Metric
        label="Current delay"
        value={`${data.live.current_delay}`}
        unit="min"
        detail={
          data.live.data_source ===
          'LIVE'
            ? 'Provider-reported delay'
            : 'Simulated demo delay'
        }
      />

      <Metric
        label="AI predicted ETA"
        value={`${nextEta?.minutes_remaining ?? '—'}`}
        unit="min"
        detail={
          nextEta
            ? `To ${nextEta.station_name}`
            : 'No prediction'
        }
      />

      <Metric
        label="Confidence"
        value={
          nextEta
            ? `${Math.round(
                nextEta.confidence *
                  100,
              )}`
            : '—'
        }
        unit="%"
        detail={
          nextEta?.model_version ||
          'Model unavailable'
        }
      />

      <Metric
        label="Predicted delay"
        value={`${data.live.predicted_delay}`}
        unit="min"
        detail={`${data.live.confidence_level} confidence`}
      />

    </div>
  )

  /*
   * ALERTS
   */
  if (section === 'alerts') {
    return (
      <AlertsPanel
        data={data}
        alerts={alerts}
        onAlertsChange={
          onAlertsChange
        }
        connectionStatus={
          connectionStatus
        }
      />
    )
  }

  /*
   * ANALYTICS
   */
  if (section === 'analytics') {
    return (
      <AnalyticsPanel
        data={data}
        trains={trains}
        alerts={alerts}
      />
    )
  }

  /*
   * SETTINGS
   */
  if (section === 'settings') {
    return (
      <SettingsPanel
        theme={theme}
        onThemeChange={
          onThemeChange
        }
        settings={settings}
        onSettingChange={onSettingChange}
      />
    )
  }

  /*
   * LIVE TRAINS
   */
  if (section === 'trains') {
    return (
      <section className="content-stack">

        <TrainFleet
          trains={trains}
          selectedId={
            data.train.train_id
          }
          onSelect={
            onTrainSelect
          }
        />

        <TrainHero
          data={data}
          progress={progress}
          status={
            connectionStatus
          }
          onMap={() =>
            onSectionChange(
              'map',
            )
          }
        />

        <section className="dashboard-grid">

          <EtaCard data={data} />

          <WeatherCard
            weather={
              data.live.weather
            }
          />

        </section>

        {stats}

        <RealtimeInfoPanel
          data={data}
          status={
            connectionStatus
          }
          lastUpdated={
            lastUpdated
          }
        />

      </section>
    )
  }

  /*
   * MAP
   */
  if (section === 'map') {
    return (
      <section className="content-stack">

        <TrainFleet
          trains={trains}
          selectedId={
            data.train.train_id
          }
          onSelect={
            onTrainSelect
          }
        />

        <MapPanel data={data} />

        <RealtimeInfoPanel
          data={data}
          status={
            connectionStatus
          }
          lastUpdated={
            lastUpdated
          }
        />

      </section>
    )
  }

  /*
   * OVERVIEW
   */
  return (
    <section className="content-stack">

      <section className="welcome-row">

        <div>

          <p className="eyebrow">
            NETWORK CONTROL ·{' '}
            {new Date().toLocaleDateString(
              undefined,
              {
                weekday:
                  'long',
              },
            )}
          </p>

          <h2>
            Railway operations
            overview
          </h2>

          <p className="muted">
            Monitor train movement,
            prediction health,
            weather and
            operational signals
            from one workspace.
          </p>

        </div>

        <button
          className="primary-button"
          onClick={() =>
            onSectionChange(
              'map',
            )
          }
          type="button"
        >
          <span className="button-glyph">
            ↗
          </span>

          Open map
        </button>

      </section>

      <TrainFleet
        trains={trains}
        selectedId={
          data.train.train_id
        }
        onSelect={
          onTrainSelect
        }
      />

      <TrainHero
        data={data}
        progress={progress}
        status={
          connectionStatus
        }
        onMap={() =>
          onSectionChange(
            'map',
          )
        }
      />

      <section className="dashboard-grid">

        <EtaCard data={data} />

        <WeatherCard
          weather={
            data.live.weather
          }
        />

      </section>

      <section className="overview-grid">

        <section className="panel station-panel">

          <PanelTitle
            eyebrow="ROUTE STATUS"
            title="Station timeline"
            action={
              <button
                className="text-button"
                onClick={() =>
                  onSectionChange(
                    'map',
                  )
                }
                type="button"
              >
                View map →
              </button>
            }
          />

          {data.route.map(
            (
              station,
              index,
            ) => (
              <div
                className="timeline-row"
                key={
                  station.station_id
                }
              >

                <span
                  className={`timeline-dot ${
                    index === 0
                      ? 'complete'
                      : index === 1
                        ? 'current'
                        : ''
                  }`}
                />

                <span className="timeline-copy">

                  <strong>
                    {
                      station.name
                    }
                  </strong>

                  <small>
                    {
                      station.code
                    }{' '}
                    ·{' '}
                    {index ===
                    0
                      ? 'Departed'
                      : index ===
                          1
                        ? 'Next stop'
                        : 'Upcoming'}
                  </small>

                </span>

                <b>
                  {index === 0
                    ? '—'
                    : data
                        .eta[
                        index - 1
                      ]
                      ? `${
                          data
                            .eta[
                            index - 1
                          ]
                            .minutes_remaining
                        } min`
                      : '—'}
                </b>

              </div>
            ),
          )}

        </section>

        <section className="panel insight-panel">

          <PanelTitle
            eyebrow="AI INSIGHT"
            title="Prediction health"
          />

          <div className="confidence-ring">

            <strong>
              {nextEta
                ? `${Math.round(
                    nextEta.confidence *
                      100,
                  )}%`
                : '—'}
            </strong>

            <span>
              confidence
            </span>

          </div>

          <p>
            ETA confidence is
            calculated from
            current telemetry,
            delay and prediction
            engine output.
          </p>

          <span className="demo-note">
            {data.live
              .data_source ===
            'LIVE'
              ? `LIVE DATA · ${
                  nextEta?.model_version ||
                  'ETA engine'
                }`
              : `DEMO DATA · ${
                  nextEta?.model_version ||
                  'ETA engine'
                }`}
          </span>

        </section>

      </section>

      {stats}

      <RealtimeInfoPanel
        data={data}
        status={
          connectionStatus
        }
        lastUpdated={
          lastUpdated
        }
      />

      <ActivityStrip
        data={data}
        status={
          connectionStatus
        }
        lastUpdated={
          lastUpdated
        }
      />

    </section>
  )
}

/*
 * TRAIN FLEET
 */
function TrainFleet({
  trains,
  selectedId,
  onSelect,
}: {
  trains: Train[]
  selectedId: string
  onSelect: (
    trainId: string,
  ) => void
}) {
  return (
    <section className="panel train-fleet">

      <PanelTitle
        eyebrow="TRAIN NETWORK"
        title={`${trains.length} trains available`}
        action={
          <span className="map-help">
            Select a train to
            inspect
          </span>
        }
      />

      <div className="train-fleet-grid">

        {trains.map(
          (train) => {
            const selected =
              train.train_id ===
              selectedId

            const delayed =
              train.status
                .toLowerCase()
                .includes(
                  'delayed',
                )

            const isLive =
              train.data_source ===
              'LIVE'

            return (
              <button
                key={
                  train.train_id
                }
                type="button"
                className={`train-fleet-card ${
                  selected
                    ? 'selected'
                    : ''
                }`}
                aria-pressed={
                  selected
                }
                onClick={() =>
                  onSelect(
                    train.train_id,
                  )
                }
              >

                <div className="fleet-card-top">

                  <span className="train-mini-icon">
                    🚆
                  </span>

                  <span
                    className={`fleet-status ${
                      delayed
                        ? 'delayed'
                        : 'on-time'
                    }`}
                  >
                    {delayed
                      ? 'DELAYED'
                      : 'ON TIME'}
                  </span>

                </div>

                <strong>
                  {
                    train.name
                  }
                </strong>

                <span className="fleet-number">
                  {
                    train.number
                  }
                </span>

                <div className="fleet-route">

                  <span>
                    {
                      train.origin
                    }
                  </span>

                  <b>
                    →
                  </b>

                  <span>
                    {
                      train.destination
                    }
                  </span>

                </div>

                <div className="fleet-meta">

                  <span
                    className={
                      isLive
                        ? 'live-source'
                        : 'demo-source'
                    }
                  >
                    {isLive
                      ? '● LIVE'
                      : '● DEMO'}
                  </span>

                  <span>
                    {selected
                      ? '✓ Selected'
                      : 'Select'}
                  </span>

                </div>

              </button>
            )
          },
        )}

      </div>
    </section>
  )
}

/*
 * STATUS BADGE
 */
function StatusBadge({
  data,
  status,
}: {
  data: Data
  status: ConnectionStatus
}) {
  const label =
    data.live.data_quality ===
    'STALE'
      ? 'STALE'
      : data.live.is_live
        ? 'LIVE'
        : data.live
              .data_quality ===
            'UNAVAILABLE'
          ? 'UNAVAILABLE'
          : 'DEMO DATA'

  return (
    <span
      className={`status-badge ${label
        .toLowerCase()
        .replace(
          ' ',
          '-',
        )}`}
    >

      <i />

      {label}

      <small>
        {status ===
        'connected'
          ? 'streaming'
          : status}
      </small>

    </span>
  )
}

/*
 * TRAIN HERO
 */
function TrainHero({
  data,
  progress,
  status,
  onMap,
}: {
  data: Data
  progress: number
  status: ConnectionStatus
  onMap: () => void
}) {
  return (
    <section className="train-hero panel">

      <div className="hero-top">

        <div className="hero-identity">

          <div className="train-emblem">
            {data.train.number.slice(
              -3,
            )}
          </div>

          <div>

            <p className="eyebrow">
              SELECTED TRAIN ·{' '}
              {
                data.train
                  .data_source
              }
            </p>

            <h2>
              {data.train.name}
            </h2>

            <p className="hero-route">
              {data.train.number}{' '}
              <span>·</span>{' '}
              {data.train.origin}{' '}
              <b>→</b>{' '}
              {data.train.destination}
            </p>

          </div>

        </div>

        <div className="hero-actions">

          <StatusBadge
            data={data}
            status={status}
          />

          <button
            className="icon-button"
            onClick={onMap}
            aria-label="Open map"
            title="Open map"
            type="button"
          >
            ↗
          </button>

        </div>

      </div>

      <div className="hero-bottom">

        <div className="hero-eta">

          <span className="eyebrow">
            ESTIMATED ARRIVAL
          </span>

          <strong>
            {data.eta[0]
              ? new Date(
                  data.eta[0]
                    .estimated_arrival,
                ).toLocaleTimeString(
                  [],
                  {
                    hour: '2-digit',
                    minute:
                      '2-digit',
                  },
                )
              : '—'}
          </strong>

          <span>
            {data.eta[0]
              ?.minutes_remaining ??
              '—'}{' '}
            min to{' '}
            {data.eta[0]
              ?.station_name ||
              'next station'}
          </span>

        </div>

        <div className="hero-stats">

          <HeroStat
            label="Speed"
            value={`${Math.round(
              data.live.speed_kmph,
            )}`}
            unit="km/h"
          />

          <HeroStat
            label="Delay"
            value={`${data.live.current_delay}`}
            unit="min"
          />

          <HeroStat
            label="Next station"
            value={
              data.eta[0]
                ?.station_name ||
              '—'
            }
          />

          <HeroStat
            label="Updated"
            value={
              data.live
                .last_updated
                ? new Date(
                    data.live
                      .last_updated,
                  ).toLocaleTimeString(
                    [],
                    {
                      hour: '2-digit',
                      minute:
                        '2-digit',
                    },
                  )
                : '—'
            }
          />

        </div>

      </div>

      <div className="progress-track">

        <span
          style={{
            width: `${progress}%`,
          }}
        />

        <b
          style={{
            left: `${progress}%`,
          }}
        />

      </div>

      <div className="hero-progress-caption">

        <span>
          Origin{' '}
          <strong>
            {data.train.origin}
          </strong>
        </span>

        <span>
          {progress}% route
          progress
        </span>

        <span>
          Destination{' '}
          <strong>
            {data.train.destination}
          </strong>
        </span>

      </div>

    </section>
  )
}

function HeroStat({
  label,
  value,
  unit,
}: {
  label: string
  value: string
  unit?: string
}) {
  return (
    <div>

      <span>
        {label}
      </span>

      <strong>
        {value}{' '}
        <small>
          {unit}
        </small>
      </strong>

    </div>
  )
}

/*
 * ETA CARD
 */
function EtaCard({
  data,
}: {
  data: Data
}) {
  const eta = data.eta[0]

  return (
    <section className="panel eta-card">

      <div className="card-heading">

        <div>

          <p className="eyebrow">
            PREDICTION WINDOW
          </p>

          <h3>
            Next arrival
          </h3>

        </div>

        <span className="soft-chip">
          {
            data.live
              .prediction_source
          }
        </span>

      </div>

      <div className="eta-value">
        {eta
          ? new Date(
              eta.estimated_arrival,
            ).toLocaleTimeString(
              [],
              {
                hour: '2-digit',
                minute:
                  '2-digit',
              },
            )
          : '—'}
      </div>

      <p className="eta-subtitle">
        {eta?.minutes_remaining ??
          '—'}{' '}
        minutes ·{' '}
        {eta?.station_name ||
          'Awaiting station'}
      </p>

      <div className="eta-details">

        <span>
          <small>
            Predicted delay
          </small>

          <b>
            {
              data.live
                .predicted_delay
            }{' '}
            min
          </b>
        </span>

        <span>
          <small>
            Confidence
          </small>

          <b>
            {
              data.live
                .confidence_level
            }{' '}
            ·{' '}
            {Math.round(
              (data.live
                .eta_confidence ??
                0) * 100,
            )}
            %
          </b>
        </span>

        <span>
          <small>
            Last updated
          </small>

          <b>
            {data.live
              .last_updated
              ? new Date(
                  data.live
                    .last_updated,
                ).toLocaleTimeString()
              : '—'}
          </b>
        </span>

      </div>

    </section>
  )
}

/*
 * WEATHER CARD
 */
function WeatherCard({
  weather: rawWeather,
}: {
  weather:
    | LivePosition['weather']
    | undefined
}) {
  const weather =
    safeWeather(rawWeather)

  const state = weather.available
    ? 'LIVE'
    : weather.source ===
        'DEMO'
      ? 'DEMO'
      : 'UNAVAILABLE'

  return (
    <section className="panel weather-card">

      <div className="card-heading">

        <div>

          <p className="eyebrow">
            ATMOSPHERIC CONDITIONS
          </p>

          <h3>
            Weather at train
          </h3>

        </div>

        <span
          className={`weather-state ${state.toLowerCase()}`}
        >
          <i />
          {state}
        </span>

      </div>

      {weather.available ? (
        <>

          <div className="weather-main">

            <strong>
              {weather.temperature ??
                '—'}
              °
            </strong>

            <span>
              {weather.weather_condition ||
                'Observed conditions'}

              <small>
                Feels like{' '}
                {weather.feels_like ??
                  '—'}
                °
              </small>
            </span>

          </div>

          <div className="weather-details">

            <span>
              Humidity{' '}
              <b>
                {weather.humidity ??
                  '—'}
                %
              </b>
            </span>

            <span>
              Wind{' '}
              <b>
                {weather.wind_speed ??
                  '—'}{' '}
                m/s
              </b>
            </span>

            <span>
              Visibility{' '}
              <b>
                {weather.visibility
                  ? `${(
                      weather.visibility /
                      1000
                    ).toFixed(
                      1,
                    )} km`
                  : '—'}
              </b>
            </span>

          </div>

        </>
      ) : (
        <div className="weather-unavailable">

          <strong>
            {weather.message}
          </strong>

          <span>
            No conditions are
            being inferred or
            simulated.
          </span>

        </div>
      )}

      <small className="source-line">
        Source ·{' '}
        {weather.source}
      </small>

    </section>
  )
}

/*
 * ACTIVITY
 */
function ActivityStrip({
  data,
  status,
  lastUpdated,
}: {
  data: Data
  status: ConnectionStatus
  lastUpdated: string
}) {
  const weather =
    safeWeather(
      data.live.weather,
    )

  return (
    <section className="activity-strip">

      <div>

        <i
          className={
            status ===
            'connected'
              ? 'pulse'
              : ''
          }
        />

        <span>
          Telemetry stream
        </span>

        <b>
          {status ===
          'connected'
            ? 'Connected'
            : status}
        </b>

      </div>

      <div>

        <i className="pulse" />

        <span>
          ETA engine
        </span>

        <b>
          Updated{' '}
          {lastUpdated
            ? new Date(
                lastUpdated,
              ).toLocaleTimeString(
                [],
                {
                  hour: '2-digit',
                  minute:
                    '2-digit',
                },
              )
            : 'waiting'}
        </b>

      </div>

      <div>

        <i
          className={
            weather.available
              ? 'pulse'
              : ''
          }
        />

        <span>
          Weather
        </span>

        <b>
          {weather.available
            ? 'Observed'
            : 'Unavailable'}
        </b>

      </div>

    </section>
  )
}

/*
 * ALERTS
 */
function AlertsPanel({
  data,
  alerts,
  onAlertsChange,
  connectionStatus,
}: {
  data: Data
  alerts: Alert[]
  onAlertsChange: (
    alerts: Alert[],
  ) => void
  connectionStatus: ConnectionStatus
}) {
  const fallbackAlert: Alert = {
    id: 'local-status',

    train_id:
      data.train.train_id,

    type:
      data.live
        .data_quality ===
      'STALE'
        ? 'DATA_STALE'
        : 'DATA_SOURCE_UNAVAILABLE',

    severity:
      data.live
        .data_quality ===
      'STALE'
        ? 'WARNING'
        : 'INFO',

    title:
      data.live
        .data_quality ===
      'STALE'
        ? 'Telemetry is stale'
        : 'Service operating normally',

    message:
      data.live
        .data_quality ===
      'STALE'
        ? 'Last known position is being displayed.'
        : data.live
              .data_source ===
            'LIVE'
          ? 'Train telemetry is being received from the configured live provider.'
          : 'This train is using clearly labelled DEMO telemetry.',

    created_at:
      new Date().toISOString(),

    acknowledged: false,

    source:
      data.train
        .data_source,

    data_quality:
      data.live
        .data_quality,

    metadata: {},
  }

  const visibleAlerts =
    alerts.length > 0
      ? alerts
      : [fallbackAlert]

  const acknowledge = (
    id: string,
  ) => {
    api
      .acknowledgeAlert(id)
      .then((updated) => {
        onAlertsChange(
          alerts.map(
            (item) =>
              item.id === id
                ? updated
                : item,
          ),
        )
      })
      .catch(() => undefined)
  }

  return (
    <section className="content-stack">

      <section className="section-intro">

        <p className="eyebrow">
          OPERATIONS SIGNALS
        </p>

        <h2>
          Alerts{' '}
          <span className="section-count">
            {
              alerts.filter(
                (item) =>
                  !item.acknowledged,
              ).length
            }{' '}
            active
          </span>
        </h2>

        <p className="muted">
          Prioritized events from
          the selected train and
          data services.
        </p>

      </section>

      <div className="alert-filters">

        <span>
          Selected train ·{' '}
          {data.train.number}
        </span>

        <span>
          Stream ·{' '}
          {connectionStatus}
        </span>

        <button
          type="button"
          onClick={() => {
            const acknowledged =
              alerts.filter(
                (item) =>
                  item.acknowledged,
              )

            if (
              acknowledged.length
            ) {
              onAlertsChange(
                acknowledged,
              )
            }
          }}
        >
          Show acknowledged
        </button>

      </div>

      <section className="alert-list">

        {visibleAlerts.map(
          (alert) => (
            <article
              className={`alert-item ${alert.severity.toLowerCase()}`}
              key={alert.id}
            >

              <span className="alert-icon">
                {alert.severity ===
                'CRITICAL'
                  ? '!'
                  : alert.severity ===
                      'WARNING'
                    ? '!'
                    : 'i'}
              </span>

              <div>

                <div className="alert-title-row">

                  <strong>
                    {
                      alert.title
                    }
                  </strong>

                  <span>
                    {
                      alert.type
                    }
                  </span>

                </div>

                <p>
                  {
                    alert.message
                  }
                </p>

                <small>
                  {new Date(
                    alert.created_at,
                  ).toLocaleTimeString()}{' '}
                  ·{' '}
                  {
                    alert.source
                  }
                </small>

              </div>

              {!alert.acknowledged &&
                alert.id !==
                  'local-status' && (
                  <button
                    className="ack-button"
                    type="button"
                    onClick={() =>
                      acknowledge(
                        alert.id,
                      )
                    }
                  >
                    Acknowledge
                  </button>
                )}

            </article>
          ),
        )}

      </section>

    </section>
  )
}

/*
 * ANALYTICS
 */
function AnalyticsPanel({
  data,
  trains,
  alerts,
}: {
  data: Data
  trains: Train[]
  alerts: Alert[]
}) {
  const confidence =
    Math.round(
      (data.live
        .eta_confidence ??
        0) * 100,
    )

  const activeTrains =
    trains.length

  const delayedTrains =
    trains.filter(
      (train) =>
        train.status
          .toLowerCase()
          .includes(
            'delayed',
          ),
    ).length

  const critical =
    alerts.filter(
      (item) =>
        item.severity ===
          'CRITICAL' &&
        !item.acknowledged,
    ).length

  const warning =
    alerts.filter(
      (item) =>
        item.severity ===
          'WARNING' &&
        !item.acknowledged,
    ).length

  return (
    <section className="content-stack">

      <section className="section-intro">

        <p className="eyebrow">
          CONTROL ROOM METRICS ·{' '}
          {
            data.train
              .data_source
          }
        </p>

        <h2>
          Analytics
        </h2>

        <p className="muted">
          Current operational
          performance across
          the available fleet.
        </p>

      </section>

      <section className="analytics-kpis">

        <div>

          <span>
            Active trains
          </span>

          <b>
            {activeTrains}
          </b>

          <small>
            Available fleet
          </small>

        </div>

        <div>

          <span>
            Delayed trains
          </span>

          <b>
            {delayedTrains}
          </b>

          <small>
            {delayedTrains
              ? 'Needs attention'
              : 'No current delays'}
          </small>

        </div>

        <div>

          <span>
            Active alerts
          </span>

          <b>
            {
              alerts.filter(
                (item) =>
                  !item.acknowledged,
              ).length
            }
          </b>

          <small>
            {critical}{' '}
            critical ·{' '}
            {warning}{' '}
            warning
          </small>

        </div>

        <div>

          <span>
            Data freshness
          </span>

          <b>
            {
              data.live
                .data_quality
            }
          </b>

          <small>
            {data.live
              .last_updated
              ? new Date(
                  data.live
                    .last_updated,
                ).toLocaleTimeString()
              : 'Unknown'}
          </small>

        </div>

      </section>

      <section className="analytics-grid">

        <article className="analytics-card">

          <span>
            Current delay
          </span>

          <strong>
            {
              data.live
                .current_delay
            }

            <small>
              {' '}
              min
            </small>
          </strong>

          <div className="spark-bars">
            <i />
            <i />
            <i />
            <i />
            <i />
            <i className="active" />
          </div>

          <small>
            {data.live
              .data_source ===
            'LIVE'
              ? 'Provider-reported operating signal'
              : 'DEMO operating signal'}
          </small>

        </article>

        <article className="analytics-card">

          <span>
            Prediction confidence
          </span>

          <strong>
            {confidence}

            <small>
              %
            </small>
          </strong>

          <div className="confidence-bar">

            <i
              style={{
                width: `${confidence}%`,
              }}
            />

          </div>

          <small>
            {
              data.live
                .confidence_level
            }{' '}
            confidence ·{' '}
            {
              data.live
                .prediction_source
            }
          </small>

        </article>

        <article className="analytics-card wide">

          <span>
            Selected train
            performance
          </span>

          <div className="route-analytics">

            <div>

              <b>
                {Math.round(
                  data.live
                    .speed_kmph,
                )}
              </b>

              <small>
                km/h current
                speed
              </small>

            </div>

            <div>

              <b>
                {
                  data.live
                    .predicted_delay
                }
              </b>

              <small>
                minutes
                predicted
                delay
              </small>

            </div>

            <div>

              <b>
                {data.eta[0]
                  ?.minutes_remaining ??
                  '—'}
              </b>

              <small>
                minutes to
                arrival
              </small>

            </div>

            <div>

              <b>
                {data.live
                  .distance_to_next_station ??
                  '—'}
              </b>

              <small>
                distance
                remaining
              </small>

            </div>

          </div>

        </article>

      </section>

    </section>
  )
}

/*
 * MAP
 */
function MapPanel({
  data,
}: {
  data: Data
}) {
  return (
    <section className="map-layout">

      <section className="panel map-panel">

        <PanelTitle
          eyebrow={`NETWORK VIEW · ${data.live.data_source}`}
          title="Railway map"
          action={
            <span className="map-help">
              Scroll to zoom ·
              drag to explore
            </span>
          }
        />

        <div className="scene-wrap">

          <RailwayMap
            train={{
              train_id: data.train.train_id,
              train_number: data.train.number,
              number: data.train.number,
              name: data.train.name,
              latitude: data.live.latitude,
              longitude: data.live.longitude,
              speed: data.live.speed_kmph,
              speed_kmph: data.live.speed_kmph,
              current_delay: data.live.current_delay,
              next_station: data.live.next_station,
              data_source: data.live.data_source,
              data_quality: data.live.data_quality,
              is_live: data.live.is_live,
              last_updated: data.live.last_updated,
              eta: data.live.eta,
            }}
            route={data.route.map((station) => ({
              station_id: station.station_id,
              name: station.name,
              code: station.code,
              sequence: station.sequence,
              latitude: station.latitude ?? null,
              longitude: station.longitude ?? null,
            }))}
            height="520px"
            className="railway-map-container"
          />

        </div>

      </section>

      <section className="panel map-summary">

        <PanelTitle
          eyebrow="TRAIN DETAILS"
          title={
            data.train.name
          }
        />

        <div className="detail-list">

          <span>
            Train number{' '}
            <b>
              {
                data.train.number
              }
            </b>
          </span>

          <span>
            Current speed{' '}
            <b>
              {Math.round(
                data.live
                  .speed_kmph,
              )}{' '}
              km/h
            </b>
          </span>

          <span>
            Current delay{' '}
            <b>
              {
                data.live
                  .current_delay
              }{' '}
              min
            </b>
          </span>

          <span>
            Next station{' '}
            <b>
              {data.eta[0]
                ?.station_name ||
                '—'}
            </b>
          </span>

          <span>
            ETA{' '}
            <b>
              {data.eta[0]
                ? new Date(
                    data.eta[0]
                      .estimated_arrival,
                  ).toLocaleTimeString(
                    [],
                    {
                      hour: '2-digit',
                      minute:
                        '2-digit',
                    },
                  )
                : '—'}
            </b>
          </span>

        </div>

        <span className="demo-note">
          {data.live
            .data_source ===
          'DEMO'
            ? 'DEMO COORDINATES · NOT LIVE GPS'
            : 'AUTHORIZED LIVE TELEMETRY'}
        </span>

      </section>

    </section>
  )
}

/*
 * REALTIME INFO
 */
function RealtimeInfoPanel({
  data,
  status,
  lastUpdated,
}: {
  data: Data
  status: ConnectionStatus
  lastUpdated: string
}) {
  const weather =
    safeWeather(
      data.live.weather,
    )

  const statusLabel =
    data.live.data_quality ===
    'STALE'
      ? 'STALE'
      : status === 'connected'
        ? 'CONNECTED'
        : status.toUpperCase()

  const weatherStatus =
    weather.available
      ? 'LIVE'
      : weather.source ===
          'DEMO'
        ? 'DEMO'
        : 'UNAVAILABLE'

  const weatherValue =
    weather.available
      ? `${
          weather.weather_condition ||
          'Observed'
        } · ${
          weather.temperature ??
          '—'
        }°C`
      : weather.message

  return (
    <section className="panel realtime-panel">

      <PanelTitle
        eyebrow="REAL-TIME TRAIN INFORMATION"
        title={
          data.train.number
        }
        action={
          <span
            className={`connection-status ${status}`}
          >
            <i />

            {statusLabel}
          </span>
        }
      />

      <div className="realtime-grid">

        <span>
          Current position{' '}
          <b>
            {data.live.latitude.toFixed(
              4,
            )}
            ,{' '}
            {data.live.longitude.toFixed(
              4,
            )}
          </b>
        </span>

        <span>
          Current speed{' '}
          <b>
            {Math.round(
              data.live
                .speed_kmph,
            )}{' '}
            km/h
          </b>
        </span>

        <span>
          Current delay{' '}
          <b>
            {
              data.live
                .current_delay
            }{' '}
            min
          </b>
        </span>

        <span>
          Predicted delay{' '}
          <b>
            {
              data.live
                .predicted_delay
            }{' '}
            min
          </b>
        </span>

        <span>
          Next station{' '}
          <b>
            {data.eta[0]
              ?.station_name ||
              '—'}
          </b>
        </span>

        <span>
          ETA{' '}
          <b>
            {data.eta[0]
              ? new Date(
                  data.eta[0]
                    .estimated_arrival,
                ).toLocaleTimeString(
                  [],
                  {
                    hour: '2-digit',
                    minute:
                      '2-digit',
                  },
                )
              : '—'}
          </b>
        </span>

        <span>
          Confidence{' '}
          <b>
            {
              data.live
                .confidence_level
            }{' '}
            ·{' '}
            {Math.round(
              (data.live
                .eta_confidence ??
                0) * 100,
            )}
            %
          </b>
        </span>

        <span>
          Last updated{' '}
          <b>
            {lastUpdated
              ? new Date(
                  lastUpdated,
                ).toLocaleTimeString()
              : 'Waiting for event'}
          </b>
        </span>

        <span>
          Data source{' '}
          <b>
            {data.live.is_live
              ? 'LIVE'
              : data.live
                    .data_quality ===
                  'STALE'
                ? 'STALE'
                : data.live
                      .data_source ===
                    'DEMO'
                  ? 'DEMO'
                  : 'UNAVAILABLE'}
          </b>
        </span>

        <span>
          Weather{' '}
          <b>
            {weatherStatus} ·{' '}
            {weatherValue}
          </b>
        </span>

        <span>
          Data quality{' '}
          <b>
            {
              data.live
                .data_quality
            }
          </b>
        </span>

      </div>

    </section>
  )
}

/*
 * METRIC
 */
function Metric({
  label,
  value,
  unit,
  detail,
}: {
  label: string
  value: string
  unit: string
  detail: string
}) {
  return (
    <article className="metric-card">

      <span>
        {label}
      </span>

      <strong>
        {value}{' '}
        <small>
          {unit}
        </small>
      </strong>

      <p>
        {detail}
      </p>

    </article>
  )
}

/*
 * PANEL TITLE
 */
function PanelTitle({
  eyebrow,
  title,
  action,
}: {
  eyebrow: string
  title: string
  action?: ReactNode
}) {
  return (
    <div className="panel-title">

      <div>

        <p className="eyebrow">
          {eyebrow}
        </p>

        <h3>
          {title}
        </h3>

      </div>

      {action}

    </div>
  )
}

/*
 * SETTINGS
 */
function SettingsPanel({
  theme,
  onThemeChange,
  settings,
  onSettingChange,
}: {
  theme: Theme
  onThemeChange: (theme: Theme) => void
  settings: Settings
  onSettingChange: <K extends keyof Settings>(
    key: K,
    value: Settings[K],
  ) => void
}) {
  return (
    <section className="content-stack settings-page">

      <section className="section-intro">

        <p className="eyebrow">
          SYSTEM CONFIGURATION
        </p>

        <h2>
          Settings
        </h2>

        <p className="muted">
          Configure dashboard behaviour,
          live railway monitoring and AI
          prediction preferences.
        </p>

      </section>

      <section className="settings-grid">

        {/* APPEARANCE */}
        <article className="panel settings-card">

          <div className="settings-card-header">

            <div className="settings-icon">
              ◐
            </div>

            <div>
              <p className="eyebrow">
                APPEARANCE
              </p>

              <h3>
                Dashboard theme
              </h3>
            </div>

          </div>

          <p className="settings-description">
            Choose how the Dynamic ETA
            control room should appear.
          </p>

          <div className="theme-options">

            {(
              [
                [
                  'system',
                  'System',
                  'Use device preference',
                ],
                [
                  'light',
                  'Light',
                  'Bright workspace',
                ],
                [
                  'dark',
                  'Dark',
                  'Low-light workspace',
                ],
              ] as [
                Theme,
                string,
                string,
              ][]
            ).map(
              (option) => {
                const [
                  value,
                  label,
                  description,
                ] = option

                return (
                  <button
                    key={value}
                    type="button"
                    className={`theme-option ${
                      theme === value
                        ? 'selected'
                        : ''
                    }`}
                    aria-pressed={
                      theme === value
                    }
                    onClick={() =>
                      onThemeChange(value)
                    }
                  >
                    <strong>
                      {label}
                    </strong>

                    <span>
                      {description}
                    </span>

                    {theme === value && (
                      <b>
                        ✓
                      </b>
                    )}
                  </button>
                )
              },
            )}

          </div>

        </article>

        {/* NOTIFICATIONS */}
        <article className="panel settings-card">

          <div className="settings-card-header">

            <div className="settings-icon">
              🔔
            </div>

            <div>
              <p className="eyebrow">
                NOTIFICATIONS
              </p>

              <h3>
                Operational alerts
              </h3>
            </div>

          </div>

          <p className="settings-description">
            Control which railway events
            should appear as notifications.
          </p>

          <SettingToggle
            label="Notifications"
            description="Enable operational notifications"
            enabled={settings.notifications}
            onChange={(value) =>
              onSettingChange(
                'notifications',
                value,
              )
            }
          />

          <SettingToggle
            label="Delay alerts"
            description="Notify when train delay changes"
            enabled={settings.delayAlerts}
            onChange={(value) =>
              onSettingChange(
                'delayAlerts',
                value,
              )
            }
          />

          <SettingToggle
            label="ETA alerts"
            description="Notify when predicted arrival changes"
            enabled={settings.etaAlerts}
            onChange={(value) =>
              onSettingChange(
                'etaAlerts',
                value,
              )
            }
          />

          <SettingToggle
            label="Critical alerts"
            description="Always show critical railway events"
            enabled={settings.criticalAlerts}
            onChange={(value) =>
              onSettingChange(
                'criticalAlerts',
                value,
              )
            }
          />

        </article>

        {/* LIVE TRACKING */}
        <article className="panel settings-card">

          <div className="settings-card-header">

            <div className="settings-icon">
              ◎
            </div>

            <div>
              <p className="eyebrow">
                LIVE TRACKING
              </p>

              <h3>
                Telemetry controls
              </h3>
            </div>

          </div>

          <p className="settings-description">
            Configure how frequently the
            dashboard refreshes operational
            information.
          </p>

          <SettingToggle
            label="Live GPS tracking"
            description="Track the selected train position"
            enabled={settings.liveTracking}
            onChange={(value) =>
              onSettingChange(
                'liveTracking',
                value,
              )
            }
          />

          <SettingToggle
            label="Automatic refresh"
            description="Refresh railway telemetry automatically"
            enabled={settings.autoRefresh}
            onChange={(value) =>
              onSettingChange(
                'autoRefresh',
                value,
              )
            }
          />

          <SettingToggle
            label="Automatic ETA updates"
            description="Update ETA from realtime events"
            enabled={settings.autoEta}
            onChange={(value) =>
              onSettingChange(
                'autoEta',
                value,
              )
            }
          />

          <div className="settings-select-row">

            <div>
              <strong>
                Refresh interval
              </strong>

              <span>
                Telemetry update frequency
              </span>
            </div>

            <select
              value={settings.refreshInterval}
              onChange={(event) =>
                onSettingChange(
                  'refreshInterval',
                  Number(event.target.value),
                )
              }
              disabled={!settings.autoRefresh}
              aria-label="Refresh interval"
            >
              <option value={5}>
                5 seconds
              </option>

              <option value={10}>
                10 seconds
              </option>

              <option value={20}>
                20 seconds
              </option>

              <option value={30}>
                30 seconds
              </option>

              <option value={60}>
                60 seconds
              </option>
            </select>

          </div>

        </article>

        {/* MAP DISPLAY */}
        <article className="panel settings-card">

          <div className="settings-card-header">

            <div className="settings-icon">
              ◈
            </div>

            <div>
              <p className="eyebrow">
                MAP DISPLAY
              </p>

              <h3>
                Railway map layers
              </h3>
            </div>

          </div>

          <p className="settings-description">
            Select the information displayed
            on the railway network map.
          </p>

          <SettingToggle
            label="Railway stations"
            description="Display stations along the route"
            enabled={settings.showStations}
            onChange={(value) =>
              onSettingChange(
                'showStations',
                value,
              )
            }
          />

          <SettingToggle
            label="Train route"
            description="Display the selected train route"
            enabled={settings.showTrainRoute}
            onChange={(value) =>
              onSettingChange(
                'showTrainRoute',
                value,
              )
            }
          />

          <SettingToggle
            label="Train position"
            description="Display current train coordinates"
            enabled={settings.showTrainPosition}
            onChange={(value) =>
              onSettingChange(
                'showTrainPosition',
                value,
              )
            }
          />

        </article>

        {/* AI ENGINE */}
        <article className="panel settings-card">

          <div className="settings-card-header">

            <div className="settings-icon">
              AI
            </div>

            <div>
              <p className="eyebrow">
                AI ENGINE
              </p>

              <h3>
                Prediction settings
              </h3>
            </div>

          </div>

          <p className="settings-description">
            Configure the information shown
            by the Dynamic ETA prediction
            engine.
          </p>

          <SettingToggle
            label="AI ETA prediction"
            description="Enable machine-learning ETA predictions"
            enabled={settings.aiPrediction}
            onChange={(value) =>
              onSettingChange(
                'aiPrediction',
                value,
              )
            }
          />

          <SettingToggle
            label="Prediction confidence"
            description="Show model confidence percentage"
            enabled={settings.predictionConfidence}
            onChange={(value) =>
              onSettingChange(
                'predictionConfidence',
                value,
              )
            }
          />

          <div className="ai-factors">

            <span>
              <b>GPS</b>
              Current position & speed
            </span>

            <span>
              <b>DELAY</b>
              Current operating delay
            </span>

            <span>
              <b>WEATHER</b>
              Atmospheric conditions
            </span>

            <span>
              <b>HISTORY</b>
              Historical delay patterns
            </span>

            <span>
              <b>CONGESTION</b>
              Network conditions
            </span>

          </div>

        </article>

        {/* SYSTEM INFORMATION */}
        <article className="panel settings-card system-card">

          <div className="settings-card-header">

            <div className="settings-icon">
              ✓
            </div>

            <div>
              <p className="eyebrow">
                SYSTEM INFORMATION
              </p>

              <h3>
                Dynamic ETA
              </h3>
            </div>

          </div>

          <div className="system-status">

            <span>
              <i className="status-online" />
              System operational
            </span>

            <b>
              v1.0.0
            </b>

          </div>

          <div className="system-details">

            <span>
              Frontend{' '}
              <b>
                React + Vite
              </b>
            </span>

            <span>
              Backend{' '}
              <b>
                FastAPI
              </b>
            </span>

            <span>
              Prediction engine{' '}
              <b>
                Machine Learning
              </b>
            </span>

            <span>
              Realtime transport{' '}
              <b>
                WebSocket
              </b>
            </span>

            <span>
              Data architecture{' '}
              <b>
                LIVE / DEMO aware
              </b>
            </span>

          </div>

          <span className="demo-note">
            Settings are saved to the backend
and cached locally on this device
          </span>

        </article>

      </section>

    </section>
  )
}

/*
 * SETTINGS TOGGLE
 */
function SettingToggle({
  label,
  description,
  enabled,
  onChange,
}: {
  label: string
  description: string
  enabled: boolean
  onChange: (
    value: boolean,
  ) => void
}) {
  return (
    <div className="setting-row">

      <div>

        <strong>
          {label}
        </strong>

        <span>
          {description}
        </span>

      </div>

      <button
        type="button"
        className={`settings-toggle ${
          enabled
            ? 'enabled'
            : ''
        }`}
        aria-pressed={enabled}
        onClick={() =>
          onChange(!enabled)
        }
      >
        <i />
      </button>

    </div>
  )
}

/*
 * PLACEHOLDER
 */


export default App