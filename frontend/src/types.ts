export type Train = {
  train_id: string
  name: string
  number: string
  status: string
  origin: string
  destination: string
  data_source: 'DEMO' | 'LIVE'
}

export type LivePosition = {
  train_id: string
  latitude: number
  longitude: number
  speed_kmph: number
  recorded_at: string
  data_source: 'DEMO' | 'LIVE'
  current_delay: number
  source: 'DEMO' | 'LIVE'
  is_live: boolean
  data_quality: 'SIMULATED' | 'LIVE' | 'STALE' | 'UNAVAILABLE'
  last_updated: string | null
  next_station: string | null
  distance_to_next_station: number | null
  weather: WeatherData
  eta: string | null
  eta_confidence: number | null
  predicted_delay: number
  confidence_level: 'HIGH' | 'MEDIUM' | 'LOW'
  prediction_source: 'LIVE' | 'DEMO' | 'UNAVAILABLE'
}

export type WeatherData = {
  temperature: number | null
  feels_like: number | null
  humidity: number | null
  weather_condition: string | null
  precipitation: number | null
  wind_speed: number | null
  visibility: number | null
  weather_delay_risk: 'LOW' | 'MEDIUM' | 'HIGH' | 'UNAVAILABLE'
  weather_last_updated: string | null
  source: string
  data_quality: 'LIVE' | 'DEMO' | 'UNAVAILABLE' | 'STALE'
  observation_timestamp: string | null
  available: boolean
  message: string
}

export type RealtimeEvent = {
  train_id: string
  train_number: string
  latitude: number
  longitude: number
  speed: number
  current_delay: number
  next_station: string
  eta: string
  timestamp: string
  data_source: 'DEMO' | 'LIVE'
  data_quality: 'SIMULATED' | 'LIVE' | 'STALE'
  weather: WeatherData
  source: 'DEMO' | 'LIVE'
  is_live: boolean
  last_updated: string
  distance_to_next_station: number
  eta_confidence: number
  predicted_delay: number
  confidence_level: 'HIGH' | 'MEDIUM' | 'LOW'
  prediction_source: 'LIVE' | 'DEMO' | 'UNAVAILABLE'
  alerts: Alert[]
}

export type Alert = {
  id: string
  train_id: string
  type: string
  severity: 'INFO' | 'WARNING' | 'CRITICAL'
  title: string
  message: string
  created_at: string
  acknowledged: boolean
  source: 'DEMO' | 'LIVE'
  data_quality: 'SIMULATED' | 'LIVE' | 'STALE' | 'UNAVAILABLE'
  metadata: Record<string, unknown>
}

export type Station = {
  station_id: string
  name: string
  code: string
  sequence: number
  data_source: 'DEMO'
}

export type EtaPrediction = {
  train_id: string
  station_id: string
  station_name: string
  next_station: string
  current_delay: number
  estimated_arrival: string
  minutes_remaining: number
  confidence: number
  model_version: string
  data_source: 'DEMO' | 'LIVE'
  predicted_delay: number
  confidence_score: number
  confidence_level: 'HIGH' | 'MEDIUM' | 'LOW'
  prediction_source: 'LIVE' | 'DEMO' | 'UNAVAILABLE'
}
