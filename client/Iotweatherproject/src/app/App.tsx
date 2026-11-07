import { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from './theme';
import { AppShell } from './AppShell';

const Overview = lazy(() => import('../pages/Overview'));
const Accuracy = lazy(() => import('../pages/Accuracy'));
const Health = lazy(() => import('../pages/Health'));

const client = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

export function App() {
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <BrowserRouter>
          <AppShell>
            <Suspense fallback={<div className="skeleton h-96" />}>
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/accuracy" element={<Accuracy />} />
                <Route path="/health" element={<Health />} />
                <Route path="*" element={<p className="text-muted">Page not found.</p>} />
              </Routes>
            </Suspense>
          </AppShell>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
