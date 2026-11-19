const BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8080'

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`${response.status}: ${detail}`)
  }
  return response.json()
}

export const getHealth = () => request('/health')
export const getLastGate = () => request('/gate/last')
export const getHistory = (limit = 10) => request(`/gate/history?limit=${limit}`)
export const getReport = () => request('/report/latest')

export const evaluate = (payload) =>
  request('/gate/evaluate', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
