// The LayerFS tab: the root session's SDK calls, replayed into the shared
// view (@dsh-layerfs/view). It follows
// the Host's /layerfs/session route while it is shown, and plays each call
// at its own time, a moment behind the run (playback.ts). A demo's speed is
// set on its demo strip (DemoStrip.tsx), not here.
import { useEffect, useRef, useState } from 'react'
import FM from '../../../../sim/simulation_engine/files.js'
import M from '../../../../sim/simulation_engine/model.js'
import * as X from '../../../model/src/index.js'
import { createFilesSource, createView, injectStyle } from '../../../view/src/index.js'
import { api, type ProjectState, type SessionView } from './api.ts'
import { CASTS, MAID_AVATARS } from './avatars.ts'
import { ProjectBoard } from './ProjectBoard.tsx'
import { Setup } from './Setup.tsx'
import type { Directories } from './InitDialog.tsx'
import { Playback, type Step } from './playback.ts'
import type { FilesSource } from './replay.ts'
import { MESSAGE } from './ui.ts'
import { useHiddenComposer } from './composer.ts'
import { storeOf } from './storage.ts'
import { followTheme } from './theme.ts'

const POLL_MS = 1500
const STORE_MS = 10_000

/** The session's view from the Host, read every POLL_MS while the page is visible. */
export function useSessionView(sessionId: string) {
  const [view, setView] = useState<SessionView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let stopped = false, timer: ReturnType<typeof setTimeout> | undefined
    const read = async () => {
      if (document.visibilityState === 'visible') {
        try {
          const next = await api.session(sessionId)
          if (!stopped) { setView(next); setError(null) }
        } catch (e) {
          if (!stopped) setError((e as Error).message)
        }
      }
      if (!stopped) timer = setTimeout(read, POLL_MS)
    }
    void read()
    return () => { stopped = true; clearTimeout(timer) }
  }, [sessionId, tick])
  return { view, error, refresh: (next?: SessionView) => { if (next) setView(next); setTick((n) => n + 1) } }
}

/** One of the session's LayerFS tabs in dsh: Work or History (`pane`). */
export function LayerFsView({ sessionId, directories, pane }: { sessionId: string, directories: () => Directories | undefined, pane: Pane }) {
  const anchor = useRef<HTMLDivElement>(null)
  useHiddenComposer(anchor)
  return <div ref={anchor} style={{ display: 'contents' }}><TabBody sessionId={sessionId} directories={directories} pane={pane} /></div>
}

type Pane = 'work' | 'history'

function TabBody({ sessionId, directories, pane }: { sessionId: string, directories: () => Directories | undefined, pane: Pane }) {
  const { view, error, refresh } = useSessionView(sessionId)
  if (!view) return <div style={MESSAGE}>{error ? `LayerFS is not available: ${error}` : 'Loading LayerFS…'}</div>
  if (!view.project) return <Setup sessionId={sessionId} view={view} onChange={refresh} directories={directories} />
  if (!view.lines.length) return <Before view={view} />
  return <Board sessionId={sessionId} view={view} error={error} pane={pane} />
}

/** Before the session's first call: the project as it is now, until the calls take over. */
function Before({ view }: { view: SessionView }) {
  const name = view.project!.name
  const [state, setState] = useState<ProjectState | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let stopped = false
    api.projectState(name).then((s) => { if (!stopped) setState(s) }, (e: Error) => { if (!stopped) setError(e.message) })
    return () => { stopped = true }
  }, [name])
  const note = view.running.length ? 'a call is running…' : 'no calls in this session yet; they show here as the agents make them'
  return (
    <div style={{ ...BAND, display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 0' }}>
      <div style={{ ...MESSAGE, padding: '0 12px', paddingBottom: 0 }}><b>{name}</b> · {note}{error ? ` · the project could not be read: ${error}` : ''}</div>
      {state ? <ProjectBoard name={name} state={state} /> : !error && <div style={{ ...MESSAGE, padding: 0, paddingBottom: 0 }}>Loading the project…</div>}
    </div>
  )
}

// The band of the conversation's scroll body that the composer leaves
// visible (dsh publishes both heights on the scroll body).
const BAND = { height: 'calc(var(--dsh-conversation-viewport-height, 100vh) - var(--dsh-composer-height, 0px))', minHeight: 320, position: 'relative' } as const

function Board({ sessionId, view, error, pane }: { sessionId: string, view: SessionView, error: string | null, pane: Pane }) {
  const host = useRef<HTMLDivElement>(null)
  const board = useRef<any>(null)
  // Files reads for this session's project; kept across rebuilds, a saved id never changes
  const files = useRef<{ session: string, source: FilesSource } | null>(null)
  if (files.current?.session !== sessionId) files.current = { session: sessionId, source: createFilesSource((kind, query) => api.files(sessionId, kind, query), () => board.current?.rerender?.()) }
  const play = useRef<{ playback: Playback, agents: string } | null>(null)
  const latest = useRef(view)
  latest.current = view
  // the project's Store sizes for store.stats, read at most every STORE_MS while calls arrive
  const store = useRef<any>(null)
  const storeRead = useRef(0)
  const lastState = useRef<ProjectState | null>(null)
  useEffect(() => {
    if (Date.now() - storeRead.current < STORE_MS) return
    storeRead.current = Date.now()
    // a read in flight is kept when more calls arrive; the board may be gone by its answer
    const name = view.project!.name
    // the sizes need only the storage read; a failed state read keeps the last one
    Promise.allSettled([api.projectStorage(name), api.projectState(name)]).then(([storage, state]) => {
      if (state.status === 'fulfilled') lastState.current = state.value
      if (storage.status !== 'fulfilled' || !storage.value.store || !lastState.current) return
      store.current = storeOf(storage.value, lastState.current, latest.current.lines)
      board.current?.rerender?.()
    })
  }, [view.lines.length, sessionId])
  // main's Layer when the session began (undefined until the project's state is read).
  // The board draws from the calls without it, and rebuilds once when it is known.
  const [start, setStart] = useState<string | null | undefined>(undefined)
  const reading = useRef(true)
  reading.current = start === undefined
  useEffect(() => {
    let stopped = false
    api.projectState(view.project!.name).then((state) => { if (!stopped) setStart(startMain(state, latest.current.lines)) }, () => { if (!stopped) setStart(null) })
    return () => { stopped = true }
  }, [sessionId])

  // the view lives as long as the tab; dsh's colour scheme sets its theme
  useEffect(() => {
    injectStyle(document)
    const root = host.current!
    let soon: ReturnType<typeof setTimeout> | undefined
    board.current = createView(root, {
      avatars: MAID_AVATARS, casts: CASTS, files: FM, lineDiff: M.lineDiff, live: false, lead: 'main', pane,
    })
    const unfollow = followTheme(root)
    board.current.rerender = () => { clearTimeout(soon); soon = setTimeout(() => board.current?.W && board.current.render(), 40) }
    return () => {
      clearTimeout(soon)
      play.current?.playback.stop()
      play.current = null
      unfollow()
      board.current.dispose()
      board.current = null
    }
  }, [sessionId])

  // new lines queue on the playback, each for its time; past ones show at once
  useEffect(() => {
    const b = board.current
    if (!b) return
    const agents = `${Object.values(view.agents).join(',')}|${start ?? ''}`
    if (!play.current || play.current.agents !== agents) {
      // a rebuild (the tab opened, or an agent was named): labels follow call
      // order; what is past applies at once, so nothing plays twice
      play.current?.playback.stop()
      const fresh = () => {
        const engine: any = new X.ReplayEngine({ project: view.project?.name ?? 'project', files: files.current!.source })
        engine.onchange = () => b.rerender()
        engine.storage = () => store.current
        if (start) engine.layer(start) // the board starts at main as the session found it
        return X.storyView(engine, { lead: 'main' })
      }
      const playback: Playback = new Playback(fresh, (W, step) => show(b, W, step, playback))
      play.current = { playback, agents }
    }
    const lines = view.lines.map((line) => ({ ...line, agent: view.agents[line.agentId] ?? line.agent }))
    const playback = play.current.playback
    playback.feed(lines, 'main').catch((e: Error) => { b.note = `The calls could not be replayed: ${e.message}` })
    if (!playback.waiting && b.W) { b.acting = runningAgents(view); b.note = noteOf(view, playback, reading.current); b.render() }
  }, [view, sessionId, start])

  /** Draws the model after a step (its agent acting, the view following it) or once caught up. */
  function show(b: any, W: any, step: Step | null, playback: Playback) {
    if (board.current !== b) return
    const v = latest.current
    b.avatar('main')
    if (step) b.avatar(step.a)
    else for (const line of v.lines) b.avatar(v.agents[line.agentId] ?? line.agent)
    b.W = W
    if (step) { b.acting = [step.a]; b.lastLoc = X.locKey(X.where(W, step.a)) } else b.acting = runningAgents(v)
    if (b.follow && W.lastTab) b.active = W.lastTab
    b.note = noteOf(v, playback, reading.current)
    b.render()
    if (step) b.animate(step.a)
  }

  useEffect(() => { if (board.current && error) board.current.note = `LayerFS is not answering: ${error}` }, [error])

  return <div ref={host} style={BAND} />
}

/**
 * The real id of main's Layer when the session began: the parent of the first
 * Layer the session published, else main's head now.
 */
function startMain(state: ProjectState, lines: any[]): string | null {
  const realOf = (label: string | null | undefined) => (label ? Object.keys(state.labels).find((real) => state.labels[real] === label) ?? null : null)
  const first = lines.find((line) => line.method === 'branch.publish' && line.layer)?.layer
  const published = first ? state.labels[first] : null
  if (published) return realOf(state.s.layers?.[published]?.parent)
  return realOf(state.s.main?.head)
}

const runningAgents = (view: SessionView) => view.running.map((line) => view.agents[line.agentId] ?? line.agent)
const noteOf = (view: SessionView, playback: Playback, reading = false) => `${view.project!.name} · ${view.lines.length} calls`
  + (reading ? ' · reading LayerFS…' : '')
  + (playback.waiting ? ` · ${playback.waiting} to play` : '') + (view.running.length ? ` · ${view.running.length} running` : '')
