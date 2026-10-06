import type { BBox, ChemDocument, ExportFormat, Health, Molecule } from './types'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* not json */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: () => request<Health>('/api/health'),

  recognize(file: Blob, signal?: AbortSignal) {
    const fd = new FormData()
    fd.append('file', file, (file as File).name || 'image.png')
    return request<ChemDocument>('/api/recognize', { method: 'POST', body: fd, signal })
  },

  recognizeRegion(file: Blob, box: BBox) {
    const fd = new FormData()
    fd.append('file', file, (file as File).name || 'image.png')
    fd.append('x0', String(box[0]))
    fd.append('y0', String(box[1]))
    fd.append('x1', String(box[2]))
    fd.append('y1', String(box[3]))
    return request<Molecule>('/api/recognize/region', { method: 'POST', body: fd })
  },

  fromMolfile: (molfile: string, id?: string, bbox?: BBox | null) =>
    request<Molecule>('/api/molecule/from-molfile', json({ molfile, id, bbox })),

  fromSmiles: (smiles: string, id?: string, bbox?: BBox | null) =>
    request<Molecule>('/api/molecule/from-smiles', json({ smiles, id, bbox })),

  async export(
    document: ChemDocument,
    format: ExportFormat,
    opts: { moleculeId?: string; reactionId?: string; contractLabels?: boolean } = {},
  ): Promise<{ blob: Blob; filename: string }> {
    const res = await fetch(
      '/api/export',
      json({
        document,
        format,
        molecule_id: opts.moleculeId ?? null,
        reaction_id: opts.reactionId ?? null,
        contract_labels: opts.contractLabels ?? true,
      }),
    )
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body?.detail || res.statusText)
    }
    const cd = res.headers.get('Content-Disposition') || ''
    const filename = /filename="([^"]+)"/.exec(cd)?.[1] || `export.${format}`
    return { blob: await res.blob(), filename }
  },

  openInChemDraw: (document: ChemDocument, moleculeId?: string, contractLabels = true) =>
    request<{ path: string; chemdraw: string | null; opened_with: string | null }>(
      '/api/chemdraw/open',
      json({ document, molecule_id: moleculeId ?? null, contract_labels: contractLabels }),
    ),
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // fallback for non-secure contexts
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
  }
}
