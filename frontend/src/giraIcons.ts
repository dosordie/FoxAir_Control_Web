import {
  Activity, Battery, BatteryCharging, Bolt, CircleHelp, CloudSun, Droplet, Droplets,
  Fan, Flame, Gauge, House, Info, Network, Plug, Power, Snowflake, Sun,
  Thermometer, TrendingUp, Type, Waves, Wind, Zap,
} from 'lucide-vue-next'

export const giraIcons = {
  knx: [Network, 'KNX'],
  temperature: [Thermometer, 'Temperatur'],
  heating: [Sun, 'Heizen'],
  cooling: [Snowflake, 'Kühlen / Abtauen'],
  hot_water: [Droplets, 'Warmwasser'],
  heat: [Flame, 'Wärme'],
  water: [Droplet, 'Wasser'],
  flow: [Waves, 'Durchfluss'],
  pressure: [Gauge, 'Druck / Drehzahl'],
  fan: [Fan, 'Lüfter'],
  air: [Wind, 'Luft'],
  weather: [CloudSun, 'Wetter'],
  electricity: [Zap, 'Elektrische Leistung'],
  current: [Plug, 'Strom / Netz'],
  voltage: [Bolt, 'Spannung'],
  energy: [Battery, 'Energie'],
  charging: [BatteryCharging, 'Speicher / Ladung'],
  efficiency: [TrendingUp, 'Effizienz / COP'],
  switch: [Power, 'Ein / Aus'],
  status: [Activity, 'Betriebsstatus'],
  house: [House, 'Gebäude'],
  info: [Info, 'Information'],
  text: [Type, 'Text'],
  unknown: [CircleHelp, 'Sonstiges'],
} as const

export function giraIcon(key?: string) {
  return key && Object.hasOwn(giraIcons, key) ? giraIcons[key as keyof typeof giraIcons][0] : giraIcons.knx[0]
}
