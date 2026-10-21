// A project like an editor: the shared view in project mode draws Files'
// tree at the picked point in a sidebar, and File, History (the chat's
// History panel, view/history.js) and Storage (the chat's storage panel) as
// tabs, from the project's LayerFS state and its Store's figures, which it
// reads here. Under it the status bar: the project's facts, when the page
// gives them, and the Store's size, which opens Storage.
import { useEffect, useRef, useState, type ReactNode } from 'react'
import FM from '../../../../sim/simulation_engine/files.js'
import M from '../../../../sim/simulation_engine/model.js'
import { createFilesSource, createView, injectStyle } from '../../../view/src/index.js'
import { api, type ProjectState, type Storage } from './api.ts'
import { CASTS, MAID_AVATARS } from './avatars.ts'
import { projectModel, type FilesSource } from './replay.ts'
import { bytes, saved, storeOf, times } from './storage.ts'
import { followTheme } from './theme.ts'
import { T } from './tokens.ts'

export function ProjectBoard({ name, state, status }: { name: string, state: ProjectState, status?: ReactNode }) {
  const host = useRef<HTMLDivElement>(null)
  const board = useRef<any>(null)
  const files = useRef<FilesSource | null>(null)
  const store = useRef<any>(null)
  const [storage, setStorage] = useState<Storage | null>(null)
  const [storageError, setStorageError] = useState<string | null>(null)

  useEffect(() => {
    injectStyle(document)
    const root = host.current!
    let soon: ReturnType<typeof setTimeout> | undefined
    board.current = createView(root, { avatars: MAID_AVATARS, casts: CASTS, files: FM, lineDiff: M.lineDiff, live: false, lead: 'main', project: true })
    board.current.rerender = () => { clearTimeout(soon); soon = setTimeout(() => board.current?.W && board.current.render(), 40) }
    const unfollow = followTheme(root)
    files.current = createFilesSource((kind, query) => api.projectFiles(name, kind, query), () => board.current?.rerender?.())
    return () => { clearTimeout(soon); unfollow(); board.current.dispose(); board.current = null }
  }, [name])

  useEffect(() => {
    const b = board.current
    if (!b) return
    const W = projectModel(state, files.current!, () => b.rerender())
    W.engine.storage = () => store.current
    for (const agent of ['main', ...new Set(Object.values(state.authors))]) b.avatar(agent)
    b.W = W
    b.render()
  }, [name, state])

  // the Store's figures, read again with the state (a Refresh)
  useEffect(() => {
    let stopped = false
    setStorage(null); setStorageError(null)
    api.projectStorage(name).then((z) => { if (!stopped) setStorage(z) }, (e: Error) => { if (!stopped) setStorageError(e.message) })
    return () => { stopped = true }
  }, [name, state])
  useEffect(() => {
    store.current = storage ? storeOf(storage, state) : null
    board.current?.rerender?.()
  }, [storage, state])

  const gain = storage ? saved(storage) : null
  return (
    <div style={{ flex: 1, minHeight: 560, display: 'flex', flexDirection: 'column', borderRadius: 'var(--dsw-radius-md)', overflow: 'hidden', border: `1px solid ${T.border}` }}>
      <div ref={host} style={{ position: 'relative', flex: 1, minHeight: 0 }} />
      <footer style={{ flex: 'none', display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '2px 16px', minWidth: 0, padding: '4px 12px', borderTop: `1px solid ${T.border}`, background: T.well, fontSize: 12 }}>
        {status}
        <span style={{ flex: 1 }} />
        <button type="button" className="lfs-chip" disabled={!storage} onClick={() => { if (board.current) board.current.ide = 'storage' }}
          title={storage ? `The Store's database is ${bytes(storage.store.file)}; every saved version as plain files would be ${bytes(storage.store.logical)}. Click for Storage.` : storageError ?? 'Reading the Store…'}
          style={{ display: 'inline-flex', gap: 4, margin: '0 -6px', padding: '0 6px', border: 0, borderRadius: T.sm, color: 'inherit', font: 'inherit', whiteSpace: 'nowrap' }}>
          {storage
            ? <><span style={{ fontWeight: 500 }}>{bytes(storage.store.file)}</span><span style={{ color: T.text2 }}>on disk{gain ? ` · ${times(gain)} smaller than raw` : ''}</span></>
            : <span style={{ color: T.caption }}>{storageError ? 'storage not read' : 'reading storage…'}</span>}
        </button>
      </footer>
    </div>
  )
}
