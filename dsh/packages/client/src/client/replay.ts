// A project's LayerFS state as the view model, with Files read on demand
// (a session's trace lines are played by playback.ts).
import * as X from '../../../model/src/index.js'
import { createFilesSource } from '../../../view/src/index.js'
import { api, type ProjectState } from './api.ts'

/** The Files pane's reads on demand (view/src/filesource.js), kept across rebuilds: a saved id never changes. */
export type FilesSource = ReturnType<typeof createFilesSource>

/**
 * A project's view model from its LayerFS state (no session): the Host's
 * labelled mirror, with Files read on demand and each node's author.
 */
export function projectModel(state: ProjectState, files: FilesSource, onchange: () => void) {
  const engine: any = new X.ReplayEngine({ project: state.s.project?.name ?? 'project', files })
  engine.m.s = { ...state.s, roots: {} }
  for (const [real, label] of Object.entries(state.labels)) { engine.m.toLabel.set(real, label); engine.m.toReal.set(label, real) }
  for (const node of [...Object.values(engine.s.commits), ...Object.values(engine.s.layers)] as any[]) node.root = node.id
  chronological(engine.s, state)
  engine.onchange = onchange
  const W: any = X.storyView(engine, { lead: 'main' })
  for (const [real, agent] of Object.entries(state.authors)) {
    const label = state.labels[real]
    if (label) W.attrib[label] = agent
  }
  return X.derive(W)
}

/**
 * Orders a snapshot's nodes by when they happened, as History draws them
 * (by slot). Commits carry their time; Layers and fork points do not, so
 * the journals' times are used, else a Layer follows its source Commit and
 * parent Layer, and a fork point follows the node it forked from and comes
 * before its Branch's first Commit.
 */
function chronological(s: any, state: ProjectState) {
  const at = new Map<string, number>()
  for (const c of Object.values(s.commits) as any[]) at.set(c.id, c.time)
  const realOf = new Map(Object.entries(state.labels).map(([r, label]) => [label, r]))
  const layers = Object.values(s.layers as Record<string, any>).sort((a, b) => a.slot - b.slot)
  for (const l of layers) {
    const after = Math.max(at.get(l.parent) ?? -Infinity, at.get(l.sourceCommit) ?? -Infinity)
    const known = state.times[realOf.get(l.id) ?? '']
    at.set(l.id, known ?? (after === -Infinity ? 0 : after + 1))
  }
  const branches = s.branchOrder.map((name: string) => s.branches[name])
  for (const b of branches) {
    const first = Math.min(...(Object.values(s.commits) as any[]).filter((c) => c.branch === b.name).map((c) => c.time))
    const after = (at.get(b.from) ?? 0) + 0.5
    at.set(`fork:${b.name}`, Math.min(state.forks[b.name] ?? after, first - 0.5))
  }
  const rank = (id: string) => (id.startsWith('fork:') ? 0 : s.commits[id] ? 1 : 2)
  const order = [...at.keys()].sort((x, y) => at.get(x)! - at.get(y)! || rank(x) - rank(y))
  order.forEach((id, slot) => {
    if (id.startsWith('fork:')) s.branches[id.slice(5)].slot = slot
    else (s.commits[id] ?? s.layers[id]).slot = slot
  })
}
