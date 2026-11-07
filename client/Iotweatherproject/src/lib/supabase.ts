import { createClient } from '@supabase/supabase-js';

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

if (!url || !key) throw new Error('VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY must be set');

// The public key can only read, as enforced by row-level security (0004_rls.sql).
export const supabase = createClient(url, key, { auth: { persistSession: false } });

export class ApiError extends Error {
  code: string;

  constructor(message: string, code: string) {
    super(message);
    this.code = code;
  }
}

export async function rpc<T>(name: string, params: Record<string, unknown> = {}): Promise<T> {
  const { data, error } = await supabase.rpc(name, params);
  if (error) throw new ApiError(error.message, error.code);
  return data as T;
}

export async function view<T>(name: string): Promise<T[]> {
  const { data, error } = await supabase.from(name).select('*');
  if (error) throw new ApiError(error.message, error.code);
  return data as T[];
}
