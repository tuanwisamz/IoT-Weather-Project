import { useEffect, useRef } from 'react';
import { echarts, type ChartOption } from './echarts';
import { useTheme } from '../app/theme';

// One wrapper for every chart: init, resize, update and dispose. A theme switch rebuilds the option.
export function Chart({ option, height = 320, label }: { option: ChartOption; height?: number; label: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<ReturnType<typeof echarts.init> | null>(null);
  const { theme } = useTheme();

  useEffect(() => {
    const instance = echarts.init(ref.current!);
    chart.current = instance;
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(ref.current!);
    return () => {
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption(option, { notMerge: true });
  }, [option, theme]);

  return <div ref={ref} role="img" aria-label={label} style={{ height, width: '100%' }} />;
}
