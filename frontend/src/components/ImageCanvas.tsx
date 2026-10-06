import { useRef, useState } from 'react'
import type { BBox, ChemDocument } from '../types'

interface Props {
  imageUrl: string
  width: number
  height: number
  doc: ChemDocument | null
  selectedId: string | null
  onSelect: (id: string | null) => void
  regionMode: boolean
  onRegion: (box: BBox) => void
}

const STATUS_COLOR = { ok: 'var(--ok)', warning: 'var(--warn)', error: 'var(--err)' } as const

export function ImageCanvas({ imageUrl, width, height, doc, selectedId, onSelect, regionMode, onRegion }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [drag, setDrag] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null)

  const toImage = (e: React.PointerEvent) => {
    const svg = svgRef.current!
    const pt = svg.createSVGPoint()
    pt.x = e.clientX
    pt.y = e.clientY
    const p = pt.matrixTransform(svg.getScreenCTM()!.inverse())
    return { x: Math.max(0, Math.min(width, p.x)), y: Math.max(0, Math.min(height, p.y)) }
  }

  const onDown = (e: React.PointerEvent) => {
    if (!regionMode) return
    const p = toImage(e)
    ;(e.target as Element).setPointerCapture(e.pointerId)
    setDrag({ x0: p.x, y0: p.y, x1: p.x, y1: p.y })
  }
  const onMove = (e: React.PointerEvent) => {
    if (!drag) return
    const p = toImage(e)
    setDrag({ ...drag, x1: p.x, y1: p.y })
  }
  const onUp = () => {
    if (!drag) return
    const box: BBox = [
      Math.min(drag.x0, drag.x1),
      Math.min(drag.y0, drag.y1),
      Math.max(drag.x0, drag.x1),
      Math.max(drag.y0, drag.y1),
    ]
    setDrag(null)
    if (box[2] - box[0] > 8 && box[3] - box[1] > 8) onRegion(box)
  }

  const stroke = Math.max(1.5, Math.max(width, height) / 600)
  const conditionIds = new Set(doc?.reactions.flatMap((r) => [...r.conditions_above, ...r.conditions_below]))
  const molRole = new Map<string, string>()
  doc?.reactions.forEach((r) => {
    r.reactants.forEach((id) => molRole.set(id, 'chất tham gia'))
    r.products.forEach((id) => molRole.set(id, 'sản phẩm'))
  })

  return (
    <div className={`canvas ${regionMode ? 'canvas--region' : ''}`}>
      <img src={imageUrl} alt="Ảnh đầu vào" draggable={false} />
      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onClick={(e) => {
          if (!regionMode && e.target === svgRef.current) onSelect(null)
        }}
      >
        <defs>
          <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--accent)" />
          </marker>
        </defs>
        {doc?.texts.map((t) => {
          if (t.text === '+') return null
          const cond = conditionIds.has(t.id)
          return (
            <rect
              key={t.id}
              x={t.bbox[0]}
              y={t.bbox[1]}
              width={t.bbox[2] - t.bbox[0]}
              height={t.bbox[3] - t.bbox[1]}
              className={cond ? 'ov-text ov-text--cond' : 'ov-text'}
              strokeWidth={stroke * 0.8}
            >
              <title>{t.text}</title>
            </rect>
          )
        })}
        {doc?.arrows.map((a) => (
          <line
            key={a.id}
            x1={a.tail[0]}
            y1={a.tail[1]}
            x2={a.head[0]}
            y2={a.head[1]}
            className="ov-arrow"
            strokeWidth={stroke * 2}
            markerEnd="url(#ah)"
          />
        ))}
        {doc?.molecules.map((m, i) =>
          m.bbox ? (
            <g
              key={m.id}
              className={`ov-mol ${selectedId === m.id ? 'ov-mol--sel' : ''}`}
              onClick={(e) => {
                if (regionMode) return
                e.stopPropagation()
                onSelect(m.id)
              }}
            >
              <rect
                x={m.bbox[0]}
                y={m.bbox[1]}
                width={m.bbox[2] - m.bbox[0]}
                height={m.bbox[3] - m.bbox[1]}
                rx={stroke * 3}
                stroke={STATUS_COLOR[m.status]}
                strokeWidth={selectedId === m.id ? stroke * 2.4 : stroke * 1.4}
              />
              <g transform={`translate(${m.bbox[0]}, ${m.bbox[1]})`}>
                <rect width={stroke * 16} height={stroke * 10} rx={stroke * 2} fill={STATUS_COLOR[m.status]} />
                <text x={stroke * 8} y={stroke * 7.2} fontSize={stroke * 7} textAnchor="middle" fill="#fff">
                  {i + 1}
                </text>
              </g>
              <title>
                {`#${i + 1} ${molRole.get(m.id) ?? ''} — ${m.formula}${m.confidence != null ? ` — ${(m.confidence * 100).toFixed(0)}%` : ''}`}
              </title>
            </g>
          ) : null,
        )}
        {drag && (
          <rect
            className="ov-drag"
            x={Math.min(drag.x0, drag.x1)}
            y={Math.min(drag.y0, drag.y1)}
            width={Math.abs(drag.x1 - drag.x0)}
            height={Math.abs(drag.y1 - drag.y0)}
            strokeWidth={stroke * 1.4}
          />
        )}
      </svg>
    </div>
  )
}
