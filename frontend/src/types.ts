export type BBox = [number, number, number, number]
export type Point = [number, number]

export interface Molecule {
  id: string
  bbox: BBox | null
  molfile: string
  smiles: string
  formula: string
  mol_weight: number
  exact_mass: number
  inchi: string
  inchikey: string
  svg: string
  confidence: number | null
  status: 'ok' | 'warning' | 'error'
  warnings: string[]
  errors: string[]
  source: 'image' | 'region' | 'edited' | 'smiles'
  alternatives: string[]
  bond_px: number | null
}

export interface TextBlock {
  id: string
  bbox: BBox
  text: string
}

export interface Arrow {
  id: string
  tail: Point
  head: Point
}

export interface Reaction {
  id: string
  reactants: string[]
  products: string[]
  agents?: string[]
  conditions_above: string[]
  conditions_below: string[]
  arrow: string | null
  reaction_smiles: string
}

export interface ChemDocument {
  id: string
  image_width: number
  image_height: number
  molecules: Molecule[]
  texts: TextBlock[]
  arrows: Arrow[]
  reactions: Reaction[]
  timings: Record<string, number>
  notices?: string[]
}

export interface Health {
  ready: boolean
  device: string | null
  accelerator: string | null
  ocr: boolean
  load_seconds: number | null
  chemdraw: string | null
  export_dir: string
}

export type ExportFormat = 'cdxml' | 'mol' | 'sdf' | 'rxn' | 'smiles'
