-- 0005_seed.sql: reference rows (architecture §7.7).

insert into locations values
  (1, 'Seri Iskandar', 4.35993, 100.98491, 4.3937, 100.9738, 25, 'Asia/Kuala_Lumpur');

insert into sources values
  ('openmeteo_current',    'model_analysis', 'Open-Meteo current (15-min)',        4.3937, 100.9738, 4,  15, 'Primary actual. Model-based, not a gauge'),
  ('openmeteo_reanalysis', 'reanalysis',     'Open-Meteo Historical Weather',      4.3937, 100.9738, 4,  60, 'Retrospective best estimate, 1–2 day delay'),
  ('metar_wmki',           'station',        'METAR WMKI Ipoh Sultan Azlan Shah',  4.568,  101.092,  26, 60, 'Real instruments; rain yes/no only'),
  ('imerg_early',          'satellite',      'GPM IMERG Early V07 (0.1°)',          4.35,   100.95,   4,  30, 'Satellite rain estimate, ~4–6 h latency');

insert into forecast_models values
  ('best_match',    'Open-Meteo Best Match', 'Open-Meteo', null,          1, true),
  ('ecmwf_ifs025',  'ECMWF IFS 0.25°',       'ECMWF',      'ecmwf_ifs025', 6, true),
  ('gfs_seamless',  'NOAA GFS',              'NOAA',       'ncep_gfs025',  6, true),
  ('icon_seamless', 'DWD ICON',              'DWD',        'dwd_icon',     6, true),
  -- optional bonus: an AI weather model and the regional JMA model (both return data)
  ('ecmwf_aifs025_single', 'ECMWF AIFS (AI model)', 'ECMWF', 'ecmwf_aifs025_single', 6, false),
  ('jma_seamless',  'JMA GSM',               'JMA',        'jma_gsm',      6, false);

insert into ml_models (name, version, algorithm, features, metrics, is_active) values
  ('rain_nowcast', 'v0-rule', 'rule', array['frac_lt_235_r25','d_bt_mean_30m_r25'],
   '{"thresholds":{"watch":0.3,"likely":0.6}}', true);   -- works from day 1, before ML training
