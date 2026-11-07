import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './theme/index.css';

const root = createRoot(document.getElementById('root')!);

// Without these the app can't start, so say why instead of leaving a blank page.
if (!import.meta.env.VITE_SUPABASE_URL || !import.meta.env.VITE_SUPABASE_ANON_KEY) {
  root.render(
    <main className="mx-auto max-w-xl p-8 text-text">
      <h1 className="text-xl font-semibold">Iskandar Weather Watch can't start</h1>
      <p className="mt-2 text-muted">
        VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are not set. Add them to client/Iotweatherproject/.env,
        or to the Render environment, and build again.
      </p>
    </main>,
  );
} else {
  const { App } = await import('./app/App');
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
