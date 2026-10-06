import type { Molecule } from '../types'

interface Props {
  mol: Molecule
  index: number
  selected: boolean
  onSelect: () => void
  onEdit: () => void
  onDelete: () => void
  onCopySmiles: () => void
  onCopyChemDraw: () => void
  onOpenChemDraw: () => void
  onUseAlternative: (smiles: string) => void
}

const STATUS_LABEL = { ok: 'Tốt', warning: 'Cần xem lại', error: 'Lỗi' } as const

export function MoleculeCard(p: Props) {
  const { mol } = p
  return (
    <article
      id={`card-${mol.id}`}
      className={`card card--${mol.status} ${p.selected ? 'card--sel' : ''}`}
      onClick={p.onSelect}
    >
      <header className="card__head">
        <span className="card__num">{p.index + 1}</span>
        <span className="card__formula" title="Công thức phân tử">
          {formatFormula(mol.formula)}
        </span>
        <span className={`badge badge--${mol.status}`}>
          {STATUS_LABEL[mol.status]}
          {mol.confidence != null && ` · ${(mol.confidence * 100).toFixed(0)}%`}
        </span>
      </header>

      <div className="card__svg" dangerouslySetInnerHTML={{ __html: mol.svg }} />

      <dl className="card__props">
        <div>
          <dt>M</dt>
          <dd>{mol.mol_weight ? `${mol.mol_weight.toFixed(2)} g/mol` : '—'}</dd>
        </div>
        <div>
          <dt>SMILES</dt>
          <dd className="mono" title={mol.smiles}>
            {mol.smiles || '—'}
          </dd>
        </div>
      </dl>

      {[...mol.errors, ...mol.warnings].length > 0 && (
        <ul className="card__msgs">
          {mol.errors.map((e, i) => (
            <li key={`e${i}`} className="msg msg--err">
              {e}
            </li>
          ))}
          {mol.warnings.map((w, i) => (
            <li key={`w${i}`} className="msg msg--warn">
              {w}
            </li>
          ))}
        </ul>
      )}

      {mol.alternatives.length > 0 && (
        <div className="card__alts">
          <span>Phương án khác:</span>
          {mol.alternatives.map((s) => (
            <button
              key={s}
              className="link mono"
              title="Dùng cấu trúc này"
              onClick={(e) => {
                e.stopPropagation()
                p.onUseAlternative(s)
              }}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <footer className="card__actions" onClick={(e) => e.stopPropagation()}>
        <button className="btn btn--sm" onClick={p.onEdit} title="Sửa cấu trúc trong trình vẽ">
          Sửa
        </button>
        <button className="btn btn--sm" onClick={p.onCopyChemDraw} title="Copy rồi ⌘V trong ChemDraw">
          Copy ChemDraw
        </button>
        <button className="btn btn--sm" onClick={p.onOpenChemDraw} title="Mở phân tử này trong ChemDraw">
          Mở ChemDraw
        </button>
        <button className="btn btn--sm" onClick={p.onCopySmiles}>
          SMILES
        </button>
        <button className="btn btn--sm btn--ghost" onClick={p.onDelete} title="Xoá phân tử">
          Xoá
        </button>
      </footer>
    </article>
  )
}

export function formatFormula(f: string) {
  if (!f) return '—'
  const parts = f.split(/(\d+)/)
  return parts.map((s, i) => (/^\d+$/.test(s) ? <sub key={i}>{s}</sub> : <span key={i}>{s}</span>))
}
