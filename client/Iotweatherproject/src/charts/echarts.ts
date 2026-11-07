// Only what the dashboard draws is registered, to keep the bundle small.
import * as echarts from 'echarts/core';
import { BarChart, LineChart } from 'echarts/charts';
import {
  AxisPointerComponent, DataZoomComponent, GridComponent, MarkAreaComponent, TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  LineChart, BarChart, GridComponent, TooltipComponent, DataZoomComponent, MarkAreaComponent, AxisPointerComponent,
  CanvasRenderer,
]);

export { echarts };
export type { EChartsCoreOption as ChartOption } from 'echarts/core';
