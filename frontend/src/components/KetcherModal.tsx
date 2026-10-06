import { useEffect, useRef, useState } from 'react'
import { Editor } from 'ketcher-react'
import { StandaloneStructServiceProvider } from 'ketcher-standalone'
import type { Ketcher } from 'ketcher-core'
import 'ketcher-react/dist/index.css'

// Indigo runs as WebAssembly inside the browser: fully offline.
const structServiceProvider = new StandaloneStructServiceProvider()

interface Props {
  title: string
  molfile: string
  onCancel: () => void
  onSave: (molfile: string) => Promise<void>
}

export default function KetcherModal({ title, molfile, onCancel, onSave }: Props) {
  const ketcherRef = useRef<Ketcher | null>(null)
  const [ready, setReady] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !saving) onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel, saving])

  const save = async () => {
    if (!ketcherRef.current) return
    setSaving(true)
    setError(null)
    try {
      const mf = await ketcherRef.current.getMolfile('v2000')
      await onSave(mf)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setSaving(false)
    }
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal__box">
        <header className="modal__head">
          <h2>{title}</h2>
          <div className="modal__actions">
            {error && <span className="msg msg--err">{error}</span>}
            <button className="btn" onClick={onCancel} disabled={saving}>
              Huỷ
            </button>
            <button className="btn btn--primary" onClick={save} disabled={!ready || saving}>
              {saving ? 'Đang lưu…' : 'Lưu cấu trúc'}
            </button>
          </div>
        </header>
        <div className="modal__editor">
          <Editor
            staticResourcesUrl=""
            structServiceProvider={structServiceProvider}
            errorHandler={(m: string) => setError(m)}
            disableMacromoleculesEditor
            onInit={(k: Ketcher) => {
              ketcherRef.current = k
              k.setMolecule(molfile)
                .then(() => setReady(true))
                .catch((e: unknown) => {
                  setError(`Không nạp được cấu trúc: ${e}`)
                  setReady(true)
                })
            }}
          />
        </div>
      </div>
    </div>
  )
}
