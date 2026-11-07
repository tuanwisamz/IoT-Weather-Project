import { useQueries, useQuery } from '@tanstack/react-query';
import { ApiError, rpc, supabase, view } from './supabase';
import { FROZEN_WINDOW } from './constants';
import type {
  CollectionWindow, CoverageRow, ForecastActualRow, Kpis, LeadMetricRow, LeaderboardRow, Next24Row, NextDayRow,
  NowRow, RainStatus, RunRow, UptimeRow,
} from './types';

const MINUTE = 60_000;
const window = { p_from: FROZEN_WINDOW.from, p_to: FROZEN_WINDOW.to };

export const useNow = () =>
  useQuery({ queryKey: ['v_now'], queryFn: () => view<NowRow>('v_now'), refetchInterval: MINUTE });

export const useRainStatus = () =>
  useQuery({
    queryKey: ['v_rain_status'],
    queryFn: async () => (await view<RainStatus>('v_rain_status'))[0] ?? null,
    refetchInterval: MINUTE,
  });

export const useCollection = () =>
  useQuery({
    queryKey: ['v_collection_window'],
    queryFn: async () => (await view<CollectionWindow>('v_collection_window'))[0] ?? null,
    refetchInterval: 2 * MINUTE,
  });

export const useKpis = () =>
  useQuery({ queryKey: ['rpc_kpis'], queryFn: () => rpc<Kpis>('rpc_kpis', window), staleTime: 10 * MINUTE });

export const useNext24 = () =>
  useQuery({ queryKey: ['rpc_next_24h'], queryFn: () => rpc<Next24Row[]>('rpc_next_24h'), refetchInterval: 10 * MINUTE });

export const useLeadMetrics = (truth: string) =>
  useQuery({
    queryKey: ['rpc_metrics_by_lead', truth],
    queryFn: () => rpc<LeadMetricRow[]>('rpc_metrics_by_lead', { ...window, p_truth: truth }),
    staleTime: 10 * MINUTE,
  });

export const useLeaderboard = (truth: string) =>
  useQuery({
    queryKey: ['rpc_leaderboard', truth],
    queryFn: () => rpc<LeaderboardRow[]>('rpc_leaderboard', { ...window, p_truth: truth }),
    staleTime: 10 * MINUTE,
  });

export const useNextDay = (leadDays: number) =>
  useQuery({
    queryKey: ['rpc_next_day', leadDays],
    queryFn: () => rpc<NextDayRow[]>('rpc_next_day', {
      p_from_date: FROZEN_WINDOW.fromDate, p_to_date: FROZEN_WINDOW.toDate, p_lead_days: leadDays,
    }),
    staleTime: 10 * MINUTE,
  });

export function useForecastActual(models: string[], variable: string, lead: number, truth: string) {
  return useQueries({
    queries: models.map((model) => ({
      queryKey: ['rpc_forecast_vs_actual', model, variable, lead, truth],
      queryFn: () => rpc<ForecastActualRow[]>('rpc_forecast_vs_actual', {
        p_model: model, p_variable: variable, p_lead_min: lead, ...window, p_truth: truth,
      }),
      staleTime: 10 * MINUTE,
    })),
  });
}

export const useCoverage = () =>
  useQuery({ queryKey: ['v_coverage_daily'], queryFn: () => view<CoverageRow>('v_coverage_daily'), refetchInterval: 2 * MINUTE });

export const useUptime = (from: string | undefined) =>
  useQuery({
    queryKey: ['rpc_uptime_daily', from],
    queryFn: () => rpc<UptimeRow[]>('rpc_uptime_daily', { p_from: from, p_to: new Date().toISOString() }),
    enabled: !!from,
    refetchInterval: 2 * MINUTE,
  });

export const useRuns = () =>
  useQuery({
    queryKey: ['ingestion_runs'],
    queryFn: async () => {
      const { data, error } = await supabase.from('ingestion_runs')
        .select('id, job, trigger, status, started_at, finished_at, rows_written, gh_run_id, error')
        .order('started_at', { ascending: false }).limit(50);
      if (error) throw new ApiError(error.message, error.code);
      return data as RunRow[];
    },
    refetchInterval: 2 * MINUTE,
  });
