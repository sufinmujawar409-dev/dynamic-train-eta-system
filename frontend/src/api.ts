import type { Alert, EtaPrediction, LivePosition, Station, Train } from './types'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) throw new Error(`API request failed (${response.status})`)
  return response.json() as Promise<T>
}

export const api = {
  trains: () => get<Train[]>('/api/trains'),
  live: (id: string) => get<LivePosition>(`/api/trains/${id}/live`),
  route: (id: string) => get<Station[]>(`/api/trains/${id}/route`),
  eta: (id: string) => get<EtaPrediction[]>(`/api/trains/${id}/eta`),
  alerts: (params = '') => get<Alert[]>(`/api/alerts${params}`),
  acknowledgeAlert: (id: string) => fetch(`${API_BASE_URL}/api/alerts/${id}/acknowledge`, { method: 'POST' }).then((response) => { if (!response.ok) throw new Error(`Alert request failed (${response.status})`); return response.json() as Promise<Alert> }),
}
