// Relative URLs let the same build run at / on Render and /echolang/ through Vercel.
const appRoot = new URL('.', window.location.href)

export const appHome = appRoot.pathname

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(new URL(`.${path}`, appRoot), init)
}
