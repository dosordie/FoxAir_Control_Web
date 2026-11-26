import {
  ArrowDownLeft, ArrowUpRight, Activity, Clock, Fan, Gauge,
  Snowflake, Sun, Thermometer, Waves, Zap,
} from 'lucide-vue-next'

export const overviewFields = {
  last_defrost: { label: 'Letztes Abtauen', icon: Snowflake, unit: '' },
  timer_m1: { label: 'Last Timer', icon: Gauge, unit: 'kW' },
  pump_feedback: { label: 'Umwälzpumpe · Rückmeldung', icon: Gauge, unit: '%' },
  flow: { label: 'Durchfluss', icon: Waves, unit: 'm³/h' },
  tank: { label: 'Warmwasser', icon: Thermometer, unit: '°C' },
  outdoor: { label: 'Außen', icon: Sun, unit: '°C' },
  return: { label: 'Eintritt', icon: ArrowDownLeft, unit: '°C' },
  supply: { label: 'Austritt', icon: ArrowUpRight, unit: '°C' },
  spread: { label: 'Spreizung VL/RL', icon: Waves, unit: 'K' },
  electrical_power: { label: 'Elektrische Leistung', icon: Zap, unit: 'kW' },
  thermal_power: { label: 'Thermische Leistung', icon: Sun, unit: 'kW' },
  cop: { label: 'COP', icon: Gauge, unit: '' },
  evaporator: { label: 'Verdampfer', icon: Snowflake, unit: '°C' },
  evi_in: { label: 'EVI-Eintritt', icon: ArrowDownLeft, unit: '°C' },
  evi_out: { label: 'EVI-Austritt', icon: ArrowUpRight, unit: '°C' },
  fan_one: { label: 'Lüfter 1', icon: Fan, unit: 'U/min' },
  fan_two: { label: 'Lüfter 2', icon: Fan, unit: 'U/min' },
  compressor_starts: { label: 'Verdichterstarts', icon: Activity, unit: '' },
  compressor_hours: { label: 'Verdichterlaufzeit', icon: Clock, unit: 'h' },
  buffer_temperature: { label: 'Puffertank', icon: Thermometer, unit: '°C' },
  low_pressure: { label: 'Niederdruck', icon: Gauge, unit: 'bar' },
  discharge_temperature: { label: 'Heißgas', icon: Thermometer, unit: '°C' },
  suction_temperature: { label: 'Sauggas', icon: Thermometer, unit: '°C' },
  compressor_frequency: { label: 'Verdichterfrequenz', icon: Gauge, unit: 'Hz' },
} as const

export type OverviewField = keyof typeof overviewFields
export type OverviewProfile = 'mobile' | 'desktop'
export type OverviewLayout = Record<OverviewProfile, string[]> & { mobile_columns: number; desktop_columns: number; mobile_glance: string[]; desktop_glance: string[] }
export const glanceActions = {
  gira: 'Alle Gira-Werte',
  power: 'Ein / Aus',
  mode: 'Modus',
  silent: 'Ruhemodus',
  parameters: 'Parameter & Einstellungen',
} as const
const defaultGlance = ['electrical_power', 'thermal_power', 'cop', ...Object.keys(glanceActions)]
export const defaultOverview: OverviewLayout = {
  mobile_glance: [...defaultGlance],
  desktop_glance: [...defaultGlance],
  mobile_columns: 3,
  desktop_columns: 8,
  mobile: ['return', 'supply', 'spread', 'flow', 'tank', 'outdoor'],
  desktop: ['flow', 'tank', 'outdoor', 'return', 'supply', 'spread'],
}
