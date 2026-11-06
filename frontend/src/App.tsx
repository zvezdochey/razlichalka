import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './layout/AppLayout'
import { NewRunPage } from './pages/newRun/NewRunPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { RunPage } from './pages/RunPage'
import { RunsListPage } from './pages/RunsListPage'
import { AppsTab } from './pages/run/AppsTab'
import { LogTab } from './pages/run/LogTab'
import { OverviewTab } from './pages/run/OverviewTab'

/** Карта маршрутов. Вкладки прогона — вложенные пути, а не состояние компонента:
 *  так ссылкой на вкладку можно поделиться и «назад» в браузере работает. */
export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/runs" replace />} />
        <Route path="runs" element={<RunsListPage />} />
        <Route path="runs/new" element={<NewRunPage />} />
        <Route path="runs/:id" element={<RunPage />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<OverviewTab />} />
          <Route path="apps" element={<AppsTab />} />
          <Route path="log" element={<LogTab />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
