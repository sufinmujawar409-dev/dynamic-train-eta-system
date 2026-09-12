import type {
  Alert,
  EtaPrediction,
  LivePosition,
  Station,
  Train,
} from './types'

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ||
  'http://127.0.0.1:8000'
).replace(/\/$/, '')

async function get<T>(
  path: string,
): Promise<T> {
  const response = await fetch(
    `${API_BASE_URL}${path}`,
  )

  if (!response.ok) {
    let message = `API request failed (${response.status})`

    try {
      const body = (await response.json()) as {
        detail?: string
      }

      if (body.detail) {
        message = body.detail
      }
    } catch {
      // Keep default HTTP error message.
    }

    throw new Error(message)
  }

  return response.json() as Promise<T>
}

export type TrainSearchResult = {
  train_id: string
  train_number: string
  train_name: string
  origin?: string
  destination?: string
  status?: string
  data_source?: string
  is_live?: boolean
  data_quality?: string
  last_updated?: string | null
}

export const api = {
  trains: () =>
    get<Train[]>('/api/trains'),

  searchTrains: (query: string) =>
    get<TrainSearchResult[]>(
      `/api/trains/search?q=${encodeURIComponent(query)}`,
    ),

  train: (id: string) =>
    get<Train>(
      `/api/trains/${encodeURIComponent(id)}`,
    ),

  live: (id: string) =>
    get<LivePosition>(
      `/api/trains/${encodeURIComponent(id)}/live`,
    ),

  route: (id: string) =>
    get<Station[]>(
      `/api/trains/${encodeURIComponent(id)}/route`,
    ),

  eta: (id: string) =>
    get<EtaPrediction[]>(
      `/api/trains/${encodeURIComponent(id)}/eta`,
    ),

  alerts: (params = '') =>
    get<Alert[]>(
      `/api/alerts${params}`,
    ),

  acknowledgeAlert: (id: string) =>
    fetch(
      `${API_BASE_URL}/api/alerts/${encodeURIComponent(id)}/acknowledge`,
      {
        method: 'POST',
      },
    ).then(async (response) => {
      if (!response.ok) {
        let message = `Alert request failed (${response.status})`

        try {
          const body = (await response.json()) as {
            detail?: string
          }

          if (body.detail) {
            message = body.detail
          }
        } catch {
          // Keep default HTTP error message.
        }

        throw new Error(message)
      }

      return response.json() as Promise<Alert>
    }),
}