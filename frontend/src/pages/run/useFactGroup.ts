import { useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

export type FactGroupState = { ref: string; label: string; key?: string; cellCount?: number; measure?: 'counts' | 'counts_distinct_apps' }
type GroupHistory = { factGroup?: FactGroupState | null; factGroupPage?: number }

/** Список группы принадлежит записи истории, поэтому сохраняется при возврате из заявки. */
export function useFactGroup() {
  const location = useLocation()
  const navigate = useNavigate()
  const state = (location.state ?? {}) as GroupHistory
  const group = state.factGroup ?? null
  const page = state.factGroupPage ?? 1
  const setGroup = useCallback((next: FactGroupState | null) => {
    navigate(location.pathname + location.search, {
      replace: true, preventScrollReset: true,
      state: { ...location.state, factGroup: next, factGroupPage: 1 },
    })
  }, [navigate, location.pathname, location.search, location.state])
  const setPage = (next: number) => {
    navigate(location.pathname + location.search, {
      replace: true, preventScrollReset: true,
      state: { ...location.state, factGroupPage: next },
    })
  }
  return { group, page, setGroup, setPage }
}
