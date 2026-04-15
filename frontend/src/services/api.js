import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const client = axios.create({
  baseURL: BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor for consistent error handling
client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'An unknown error occurred'
    return Promise.reject(new Error(message))
  }
)

/**
 * Fetch the composite sentiment score, label, component breakdown, and history.
 * @returns {Promise<{score: number, label: string, components: object, history: Array}>}
 */
export async function fetchComposite() {
  return client.get('/api/composite')
}

/**
 * Fetch VIX (Volatility Index) data including current value, normalized score, signal, and history.
 * @returns {Promise<{current: number, normalized: number, signal: string, history: Array}>}
 */
export async function fetchVix() {
  return client.get('/api/vix')
}

/**
 * Fetch Put/Call ratio data including current value, normalized score, signal, and history.
 * @returns {Promise<{current: number, normalized: number, signal: string, history: Array}>}
 */
export async function fetchPutCall() {
  return client.get('/api/put-call')
}

/**
 * Fetch sector performance data for all 11 sector ETFs and overall breadth score.
 * @returns {Promise<{sectors: Array, breadth_score: number}>}
 */
export async function fetchSectors() {
  return client.get('/api/sectors')
}

/**
 * Fetch the CNN Fear & Greed index score, label, and detailed component breakdown.
 * @returns {Promise<{score: number, label: string, components: Array}>}
 */
export async function fetchFearGreed() {
  return client.get('/api/fear-greed')
}
