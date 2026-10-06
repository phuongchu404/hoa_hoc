import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, copyText, downloadBlob } from './api'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ImageCanvas } from './components/ImageCanvas'
import { MoleculeCard } from './components/MoleculeCard'
import { ReactionRow } from './components/ReactionRow'
import type { BBox, ChemDocument, ExportFormat, Health, Molecule } from './types'

const KetcherModal = lazy(() => import('./components/KetcherModal'))

type Toast = { id: number; kind: 'ok' | 'err' | 'info'; text: string }

const ACCEPT = 'image/png,image/jpeg,image/gif,image/bmp,image/tiff,image/webp'

function imageFromClipboard(data: DataTransfer | null): File | null {
  if (!data) return null
  for (const item of Array.from(data.items || [])) {
    if (item.kind === 'file' && item.type.startsWith('image/')) {
      const f = item.getAsFile()
      if (f) return f
    }
  }
  return Array.from(data.files || []).find((f) => f.type.startsWith('image/')) ?? null
}

function loadPref(key: string, fallback: boolean) {
  try {
    const v = localStorage.getItem(key)
    return v == null ? fallback : v === '1'
  } catch {
    return fallback
  }
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [file, setFile] = useState<Blob | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null)
  const [doc, setDoc] = useState<ChemDocument | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [regionMode, setRegionMode] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [contract, setContract] = useState(() => loadPref('contractLabels', true))
  const [toasts, setToasts] = useState<Toast[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [smilesInput, setSmilesInput] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const toast = useCallback((kind: Toast['kind'], text: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, kind, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'err' ? 7000 : 3500)
  }, [])

  // ---- backend status (models take a few seconds to load at startup)
  useEffect(() => {
    let stop = false
    let delay = 600
    const poll = async () => {
      try {
        const h = await api.health()
        if (stop) return
        setHealth(h)
        if (!h.ready) setTimeout(poll, delay)
      } catch {
        if (!stop) setTimeout(poll, (delay = Math.min(delay * 1.5, 4000)))
      }
    }
    poll()
    return () => {
      stop = true
    }
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem('contractLabels', contract ? '1' : '0')
    } catch {
      /* private mode */
    }
  }, [contract])

  // ---- image intake: file picker, drag & drop, paste
  const handleFile = useCallback(
    async (f: Blob) => {
      if (!f.type.startsWith('image/')) {
        toast('err', 'File không phải ảnh. Hỗ trợ PNG, JPG, GIF, BMP, TIFF, WEBP.')
        return
      }
      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      const url = URL.createObjectURL(f)
      setImageUrl((old) => {
        if (old) URL.revokeObjectURL(old)
        return url
      })
      const img = new Image()
      img.onload = () => setImgSize({ w: img.naturalWidth, h: img.naturalHeight })
      img.src = url
      setFile(f)
      setDoc(null)
      setSelectedId(null)
      setRegionMode(false)
      setError(null)
      setBusy('Đang nhận dạng…')
      try {
        const d = await api.recognize(f, ctrl.signal)
        setDoc(d)
        const issues = d.molecules.filter((m) => m.status !== 'ok').length
        toast(
          issues ? 'info' : 'ok',
          `Nhận dạng ${d.molecules.length} phân tử, ${d.reactions.length} phản ứng trong ${d.timings.total?.toFixed(1)} s` +
            (issues ? ` — ${issues} cấu trúc cần xem lại` : ''),
        )
      } catch (e) {
        if ((e as Error).name === 'AbortError') return
        setError((e as Error).message)
      } finally {
        if (abortRef.current === ctrl) setBusy(null)
      }
    },
    [toast],
  )

  // Paste an image from anywhere on the page. Listening on document in the
  // capture phase means no focused field or editor can swallow the event; an
  // image on the clipboard always wins over text pasting.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      if (editingId) return // Ketcher handles its own clipboard
      const f = imageFromClipboard(e.clipboardData)
      if (!f) return
      e.preventDefault()
      e.stopPropagation()
      handleFile(f)
    }
    document.addEventListener('paste', onPaste, true)
    return () => document.removeEventListener('paste', onPaste, true)
  }, [handleFile, editingId])

  const pasteFromClipboard = async () => {
    try {
      const items = await navigator.clipboard.read()
      for (const item of items) {
        const type = item.types.find((t) => t.startsWith('image/'))
        if (type) {
          const blob = await item.getType(type)
          handleFile(new File([blob], `clipboard.${type.split('/')[1] || 'png'}`, { type }))
          return
        }
      }
      toast('info', 'Clipboard không có ảnh. Hãy copy ảnh (hoặc chụp màn hình bằng ⌘⇧⌃4) rồi thử lại.')
    } catch {
      toast('info', 'Trình duyệt chặn đọc clipboard — hãy nhấn ⌘V trên trang.')
    }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setRegionMode(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // ---- document helpers
  const molIndex = useMemo(() => new Map(doc?.molecules.map((m, i) => [m.id, i]) ?? []), [doc])
  const texts = useMemo(() => new Map(doc?.texts.map((t) => [t.id, t]) ?? []), [doc])

  const withReactionSmiles = (d: ChemDocument): ChemDocument => {
    const smi = new Map(d.molecules.map((m) => [m.id, m.smiles]))
    const join = (ids: string[]) => ids.map((i) => smi.get(i)).filter(Boolean).join('.')
    return {
      ...d,
      reactions: d.reactions.map((r) => ({
        ...r,
        reaction_smiles: `${join(r.reactants)}>${join(r.agents ?? [])}>${join(r.products)}`,
      })),
    }
  }

  const replaceMolecule = (id: string, mol: Molecule) =>
    setDoc((d) => {
      if (!d) return d
      const old = d.molecules.find((m) => m.id === id)
      const next = { ...mol, id, bbox: mol.bbox ?? old?.bbox ?? null }
      return withReactionSmiles({ ...d, molecules: d.molecules.map((m) => (m.id === id ? next : m)) })
    })

  const deleteMolecule = (id: string) =>
    setDoc((d) =>
      d
        ? withReactionSmiles({
            ...d,
            molecules: d.molecules.filter((m) => m.id !== id),
            reactions: d.reactions.map((r) => ({
              ...r,
              reactants: r.reactants.filter((x) => x !== id),
              products: r.products.filter((x) => x !== id),
              agents: (r.agents ?? []).filter((x) => x !== id),
            })),
          })
        : d,
    )

  const onRegion = async (box: BBox) => {
    if (!file) return
    setRegionMode(false)
    setBusy('Đang nhận dạng vùng chọn…')
    try {
      const mol = await api.recognizeRegion(file, box)
      setDoc((d) =>
        d
          ? { ...d, molecules: [...d.molecules, mol] }
          : {
              id: '',
              image_width: imgSize?.w ?? 0,
              image_height: imgSize?.h ?? 0,
              molecules: [mol],
              texts: [],
              arrows: [],
              reactions: [],
              timings: {},
            },
      )
      setSelectedId(mol.id)
      toast('ok', `Đã thêm phân tử ${mol.formula || ''}`)
    } catch (e) {
      toast('err', (e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const addFromSmiles = async () => {
    const s = smilesInput.trim()
    if (!s) return
    try {
      const mol = await api.fromSmiles(s)
      setDoc((d) =>
        d
          ? { ...d, molecules: [...d.molecules, mol] }
          : { id: '', image_width: 0, image_height: 0, molecules: [mol], texts: [], arrows: [], reactions: [], timings: {} },
      )
      setSmilesInput('')
      setSelectedId(mol.id)
    } catch (e) {
      toast('err', (e as Error).message)
    }
  }

  // ---- exports
  const copyForChemDraw = async (moleculeId?: string) => {
    if (!doc) return
    try {
      const { blob } = await api.export(doc, 'cdxml', { moleculeId, contractLabels: contract })
      await copyText(await blob.text())
      toast('ok', 'Đã copy — chuyển sang ChemDraw và nhấn ⌘V')
    } catch (e) {
      toast('err', (e as Error).message)
    }
  }

  const openChemDraw = async (moleculeId?: string) => {
    if (!doc) return
    try {
      const r = await api.openInChemDraw(doc, moleculeId, contract)
      if (r.opened_with) toast('ok', `Đã mở bằng ${r.opened_with}`)
      else toast('info', `Đã lưu ${r.path} (không tìm thấy ChemDraw)`)
    } catch (e) {
      toast('err', (e as Error).message)
    }
  }

  const download = async (format: ExportFormat, opts: { moleculeId?: string; reactionId?: string } = {}) => {
    if (!doc) return
    try {
      const { blob, filename } = await api.export(doc, format, { ...opts, contractLabels: contract })
      downloadBlob(blob, filename)
    } catch (e) {
      toast('err', (e as Error).message)
    }
  }

  const select = (id: string | null) => {
    setSelectedId(id)
    if (id) document.getElementById(`card-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }

  const editing = doc?.molecules.find((m) => m.id === editingId) ?? null
  const inReaction = new Set(doc?.reactions.flatMap((r) => [...r.reactants, ...r.products, ...(r.agents ?? [])]))
  const standalone = doc?.molecules.filter((m) => !inReaction.has(m.id)) ?? []

  const renderMolecule = (id: string) => {
    const m = doc?.molecules.find((x) => x.id === id)
    if (!m) return null
    return (
      <MoleculeCard
        key={m.id}
        mol={m}
        index={molIndex.get(m.id) ?? 0}
        selected={selectedId === m.id}
        onSelect={() => setSelectedId(m.id)}
        onEdit={() => setEditingId(m.id)}
        onDelete={() => deleteMolecule(m.id)}
        onCopySmiles={async () => {
          await copyText(m.smiles)
          toast('ok', 'Đã copy SMILES')
        }}
        onCopyChemDraw={() => copyForChemDraw(m.id)}
        onOpenChemDraw={() => openChemDraw(m.id)}
        onUseAlternative={async (s) => {
          try {
            replaceMolecule(m.id, await api.fromSmiles(s, m.id, m.bbox))
          } catch (e) {
            toast('err', (e as Error).message)
          }
        }}
      />
    )
  }

  const ready = health?.ready
  return (
    <div
      className={`app ${dragOver ? 'app--drag' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragOver(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        const f = e.dataTransfer.files?.[0]
        if (f) handleFile(f)
      }}
    >
      <header className="topbar">
        <div className="brand">
          <svg viewBox="0 0 32 32" width="22" height="22" aria-hidden>
            <polygon points="16,3 27,9.5 27,22.5 16,29 5,22.5 5,9.5" fill="none" stroke="currentColor" strokeWidth="2.5" />
            <line x1="9" y1="11.5" x2="16" y2="7.5" stroke="currentColor" strokeWidth="2" />
          </svg>
          <span>
            ChemImage <span className="brand__arrow">→</span> ChemDraw
          </span>
        </div>
        <div className="status">
          <span className={`dot ${ready ? 'dot--ok' : 'dot--wait'}`} />
          {ready
            ? `Sẵn sàng · ${health?.accelerator ? `${health.accelerator.toUpperCase()}+CPU` : 'CPU'} · offline`
            : health
              ? 'Đang nạp model…'
              : 'Đang kết nối backend…'}
          {health && (
            <span className={`chip ${health.chemdraw ? 'chip--ok' : ''}`} title={health.chemdraw ?? ''}>
              {health.chemdraw ? 'ChemDraw ✓' : 'Chưa thấy ChemDraw'}
            </span>
          )}
        </div>
        <div className="topbar__actions">
          <button className="btn" onClick={pasteFromClipboard} title="Dán ảnh đang có trong clipboard (hoặc nhấn ⌘V)">
            Dán ảnh ⌘V
          </button>
          <button className="btn" onClick={() => fileInput.current?.click()}>
            Chọn ảnh
          </button>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPT}
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) handleFile(f)
              e.target.value = ''
            }}
          />
        </div>
      </header>

      {!imageUrl ? (
        <main className="empty">
          <button className="drop" onClick={() => fileInput.current?.click()}>
            <svg viewBox="0 0 48 48" width="48" height="48" aria-hidden>
              <path d="M24 32V12m0 0l-8 8m8-8l8 8" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M8 30v8h32v-8" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
            <strong>Kéo thả ảnh vào đây, dán bằng ⌘V, hoặc bấm để chọn file</strong>
            <span>Ảnh cấu trúc, sơ đồ phản ứng, trang tài liệu — mọi xử lý chạy trên máy này</span>
          </button>
        </main>
      ) : (
        <main className="split">
          <section className="pane pane--image">
            <div className="pane__bar">
              <button
                className={`btn btn--sm ${regionMode ? 'btn--primary' : ''}`}
                onClick={() => setRegionMode((v) => !v)}
                disabled={!file || !!busy}
                title="Kéo chuột quanh một cấu trúc bị bỏ sót để nhận dạng"
              >
                {regionMode ? 'Kéo chọn vùng… (Esc để huỷ)' : '+ Chọn vùng'}
              </button>
              {doc && (
                <span className="legend">
                  <i className="lg lg--ok" /> tốt <i className="lg lg--warn" /> cần xem <i className="lg lg--err" /> lỗi
                  <i className="lg lg--cond" /> điều kiện
                </span>
              )}
            </div>
            {imgSize && (
              <ImageCanvas
                imageUrl={imageUrl}
                width={imgSize.w}
                height={imgSize.h}
                doc={doc}
                selectedId={selectedId}
                onSelect={select}
                regionMode={regionMode}
                onRegion={onRegion}
              />
            )}
          </section>

          <section className="pane pane--results">
            {busy && (
              <div className="busy">
                <span className="spinner" /> {busy}
              </div>
            )}
            {error && (
              <div className="alert">
                <strong>Lỗi:</strong> {error}
                {file && (
                  <button className="btn btn--sm" onClick={() => handleFile(file)}>
                    Thử lại
                  </button>
                )}
              </div>
            )}

            {doc && (
              <>
                <div className="actions">
                  <button className="btn btn--primary" onClick={() => openChemDraw()} disabled={!doc.molecules.length}>
                    Mở tất cả trong ChemDraw
                  </button>
                  <button className="btn" onClick={() => copyForChemDraw()} disabled={!doc.molecules.length}>
                    Copy cho ChemDraw
                  </button>
                  <details className="menu">
                    <summary className="btn">Tải xuống ▾</summary>
                    <div className="menu__list">
                      <button onClick={() => download('cdxml')}>ChemDraw (.cdxml)</button>
                      <button onClick={() => download('sdf')}>Tất cả phân tử (.sdf)</button>
                      <button onClick={() => download('rxn')} disabled={!doc.reactions.length}>
                        Phản ứng (.rxn)
                      </button>
                      <button onClick={() => download('smiles')}>SMILES (.smi)</button>
                    </div>
                  </details>
                  <label className="toggle" title="Giữ CO2Et, Ph, Me… dạng nhãn viết tắt như trong ảnh">
                    <input type="checkbox" checked={contract} onChange={(e) => setContract(e.target.checked)} />
                    Giữ nhãn viết tắt
                  </label>
                  <span className="meta">
                    {doc.molecules.length} phân tử · {doc.reactions.length} phản ứng
                    {doc.timings.total != null && ` · ${doc.timings.total.toFixed(2)} s`}
                  </span>
                </div>

                {doc.notices?.map((n, i) => (
                  <div key={i} className="alert alert--info">
                    {n}
                  </div>
                ))}

                {doc.reactions.map((r, i) => (
                  <ReactionRow
                    key={r.id}
                    index={i}
                    reaction={r}
                    texts={texts}
                    renderMolecule={renderMolecule}
                    onTextChange={(id, text) =>
                      setDoc((d) => (d ? { ...d, texts: d.texts.map((t) => (t.id === id ? { ...t, text } : t)) } : d))
                    }
                    onCopySmiles={async () => {
                      await copyText(r.reaction_smiles)
                      toast('ok', 'Đã copy reaction SMILES')
                    }}
                    onExportRxn={() => download('rxn', { reactionId: r.id })}
                  />
                ))}

                {standalone.length > 0 && (
                  <section className="reaction">
                    <header className="reaction__head">
                      <h3>{doc.reactions.length ? 'Phân tử khác' : 'Phân tử'}</h3>
                    </header>
                    <div className="grid">{standalone.map((m) => renderMolecule(m.id))}</div>
                  </section>
                )}

                {!doc.molecules.length && !busy && (
                  <div className="alert alert--info">
                    Không tìm thấy cấu trúc nào. Dùng “+ Chọn vùng” để khoanh vùng cấu trúc cần nhận dạng.
                  </div>
                )}

                <div className="add-smiles">
                  <input
                    value={smilesInput}
                    onChange={(e) => setSmilesInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && addFromSmiles()}
                    placeholder="Thêm phân tử từ SMILES…"
                    spellCheck={false}
                  />
                  <button className="btn btn--sm" onClick={addFromSmiles} disabled={!smilesInput.trim()}>
                    Thêm
                  </button>
                </div>
              </>
            )}
          </section>
        </main>
      )}

      {editing && (
        <ErrorBoundary
          fallback={(err) => (
            <div className="modal">
              <div className="alert">
                <strong>Không mở được trình vẽ:</strong> {err.message}
                <button className="btn btn--sm" onClick={() => setEditingId(null)}>
                  Đóng
                </button>
              </div>
            </div>
          )}
        >
        <Suspense
          fallback={
            <div className="modal">
              <div className="busy">
                <span className="spinner" /> Đang mở trình vẽ…
              </div>
            </div>
          }
        >
          <KetcherModal
            title={`Sửa phân tử #${(molIndex.get(editing.id) ?? 0) + 1}`}
            molfile={editing.molfile}
            onCancel={() => setEditingId(null)}
            onSave={async (mf) => {
              const mol = await api.fromMolfile(mf, editing.id, editing.bbox)
              replaceMolecule(editing.id, mol)
              setEditingId(null)
              toast('ok', 'Đã cập nhật cấu trúc')
            }}
          />
        </Suspense>
        </ErrorBoundary>
      )}

      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.kind}`}>
            {t.text}
          </div>
        ))}
      </div>
    </div>
  )
}
