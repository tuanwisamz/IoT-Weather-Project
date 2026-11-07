import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { LEAD_STOPS, MODELS, TRUTHS, VARIABLES } from './constants';

const DEFAULT_MODELS = MODELS.map((m) => m.code);

// Accuracy's filters live in the URL, so any view can be shared or bookmarked.
export function useAccuracyFilters() {
  const [params, setParams] = useSearchParams();

  const variable = VARIABLES.some((v) => v.code === params.get('var')) ? params.get('var')! : VARIABLES[0].code;
  const truth = TRUTHS.some((t) => t.code === params.get('truth')) ? params.get('truth')! : TRUTHS[0].code;
  const leadParam = Number(params.get('lead'));
  const lead = LEAD_STOPS.includes(leadParam) ? leadParam : LEAD_STOPS[0];
  const fromUrl = params.get('models')?.split(',').filter((c) => MODELS.some((m) => m.code === c)) ?? [];
  const models = fromUrl.length ? fromUrl : DEFAULT_MODELS;

  const update = useCallback((key: string, value: string) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set(key, value);
      return next;
    }, { replace: true });
  }, [setParams]);

  return { variable, truth, lead, models, update };
}
