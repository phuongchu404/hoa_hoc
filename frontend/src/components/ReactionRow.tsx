import { Fragment, type ReactNode } from 'react'
import type { Reaction, TextBlock } from '../types'

interface Props {
  index: number
  reaction: Reaction
  texts: Map<string, TextBlock>
  renderMolecule: (id: string) => ReactNode
  onTextChange: (id: string, text: string) => void
  onCopySmiles: () => void
  onExportRxn: () => void
}

export function ReactionRow({ index, reaction, texts, renderMolecule, onTextChange, onCopySmiles, onExportRxn }: Props) {
  const cond = (ids: string[]) =>
    ids
      .map((id) => texts.get(id))
      .filter((t): t is TextBlock => !!t)
      .map((t) => (
        <textarea
          key={t.id}
          className="cond"
          value={t.text}
          rows={Math.max(1, t.text.split('\n').length)}
          onChange={(e) => onTextChange(t.id, e.target.value)}
          spellCheck={false}
          aria-label="Điều kiện phản ứng"
        />
      ))

  const side = (ids: string[]) =>
    ids.map((id, i) => (
      <Fragment key={id}>
        {i > 0 && <span className="plus">+</span>}
        {renderMolecule(id)}
      </Fragment>
    ))

  return (
    <section className="reaction">
      <header className="reaction__head">
        <h3>Phản ứng {index + 1}</h3>
        <div className="reaction__tools">
          <button className="btn btn--sm" onClick={onCopySmiles} title={reaction.reaction_smiles}>
            Copy reaction SMILES
          </button>
          <button className="btn btn--sm" onClick={onExportRxn}>
            Tải .rxn
          </button>
        </div>
      </header>
      <div className="reaction__body">
        <div className="reaction__side">{side(reaction.reactants)}</div>
        <div className="reaction__arrow">
          {!!reaction.agents?.length && (
            <div className="reaction__agents">{reaction.agents.map((id) => renderMolecule(id))}</div>
          )}
          <div className="reaction__cond reaction__cond--above">{cond(reaction.conditions_above)}</div>
          <div className="arrow" aria-hidden />
          <div className="reaction__cond reaction__cond--below">{cond(reaction.conditions_below)}</div>
        </div>
        <div className="reaction__side">{side(reaction.products)}</div>
      </div>
    </section>
  )
}
