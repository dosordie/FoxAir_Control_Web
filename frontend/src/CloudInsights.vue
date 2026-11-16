<script setup lang="ts">
import {computed,ref} from 'vue'
import {api} from './api'
defineProps<{admin:boolean}>()
const busy=ref(false),error=ref(''),address=ref('2046'),days=ref(1)
const history=ref<Awaited<ReturnType<typeof api.cloudHistory>>|null>(null)
const ota=ref<Awaited<ReturnType<typeof api.cloudInsight>>|null>(null)
const metadata=ref<Awaited<ReturnType<typeof api.cloudInsight>>|null>(null)
async function load(kind:'history'|'ota'|'metadata'){
 if(busy.value)return
 busy.value=true;error.value=''
 try{
  if(kind==='history'){
   const end=new Date(),start=new Date(end.getTime()-days.value*86400000)
   const format=(d:Date)=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Etc/GMT-1',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(d)
   history.value=await api.cloudHistory(address.value,format(start),format(end),days.value>1?'month':'day')
  }else if(kind==='ota')ota.value=await api.cloudInsight(kind)
  else metadata.value=await api.cloudInsight(kind)
 }catch(e){error.value=e instanceof Error?e.message:'Cloud-Abfrage fehlgeschlagen'}
 finally{busy.value=false}
}
const chart=computed(()=>{
 const points=history.value?.points||[]
 if(points.length<2)return ''
 const low=Math.min(...points.map(p=>p.value)),high=Math.max(...points.map(p=>p.value))
 const first=new Date(points[0]!.time).getTime(),last=new Date(points[points.length-1]!.time).getTime()
 return points.map(p=>`${20+(new Date(p.time).getTime()-first)/Math.max(1,last-first)*560},${150-(p.value-low)/Math.max(.1,high-low)*130}`).join(' ')
})
</script>
<template>
 <section class="settings-panel panel">
  <span class="section-caption">PHNIX CLOUD · LESEND</span><h2>Verlauf und Geräteinformationen</h2>
  <p v-if="!admin" class="section-hint">Zum Abrufen als Administrator anmelden.</p>
  <p v-if="error" role="alert" class="read-error">{{ error }}</p>
  <div class="cloud-extra-controls">
   <label>Messwert<select v-model="address" class="settings-input"><option value="2046">Vorlauf</option><option value="2045">Rücklauf</option><option value="2047">Warmwasser</option><option value="2048">Außen</option><option value="2078+9">Tages-Stromverbrauch</option></select></label>
   <label>Zeitraum (UTC+1)<select v-model.number="days" class="settings-input"><option :value="1">24 Stunden</option><option :value="7">7 Tage</option><option :value="30">30 Tage</option></select></label>
   <button class="outlined-action" :disabled="busy||!admin" @click="load('history')">Verlauf laden</button>
  </div>
  <div v-if="history">
   <p class="section-hint">{{ history.points.length }} Messpunkte · {{ history.unit }} · Abfrage {{ new Date(history.checked_at).toLocaleString('de-DE') }} {{ history.cached?'(Cache)':'' }}</p>
   <p v-if="history.points.length" class="section-hint">Wertebereich: {{ Math.min(...history.points.map(p=>p.value)).toLocaleString('de-DE') }}–{{ Math.max(...history.points.map(p=>p.value)).toLocaleString('de-DE') }} {{ history.unit }}</p>
   <svg v-if="chart" viewBox="0 0 600 175" class="history-chart" role="img" aria-label="Zeitlicher Verlauf der Cloud-Messwerte"><path d="M20 10V150H585" fill="none" stroke="#c5cbd2"/><polyline :points="chart" fill="none" stroke="#e87f2d" stroke-width="3"/><text x="20" y="170" font-size="11">{{ history.points[0]?.time.slice(5,16) }}</text><text x="580" y="170" text-anchor="end" font-size="11">{{ history.points[history.points.length-1]?.time.slice(5,16) }}</text></svg>
   <p v-if="history.points.some(p=>p.incomplete)" class="section-hint">Der laufende Tag kann unvollständig sein. Ein dort gemeldeter Nullwert ist kein bestätigter Nullverbrauch.</p>
   <p v-if="!history.points.length">Keine Messpunkte im gewählten Zeitraum.</p>
   <details><summary>Messpunkte mit Zeitstempeln</summary><div class="history-points"><div v-for="point in history.points" :key="point.time"><time>{{ point.time }}</time><strong>{{ point.value.toLocaleString('de-DE') }} {{ history.unit }}</strong><span v-if="point.incomplete">Laufender Tag – möglicherweise unvollständig</span></div></div></details>
  </div>
  <div class="cloud-extra-controls"><button class="outlined-action" :disabled="busy||!admin" @click="load('ota')">Geräte-Firmware: Verfügbarkeit prüfen</button><button class="outlined-action" :disabled="busy||!admin" @click="load('metadata')">Hersteller-Servicekatalog laden</button></div>
  <p v-if="ota" role="status">{{ ota.available?'Firmwareangebot gemeldet ('+ota.count+').':'Kein Firmwareupdate angeboten.' }} Geprüft {{ new Date(ota.checked_at).toLocaleString('de-DE') }}. Es wird kein Update gestartet.</p>
  <details v-if="metadata"><summary>{{ metadata.items?.length||0 }} Hersteller-Einträge</summary><p class="section-hint">{{ metadata.source }}</p><div class="history-points"><div v-for="(row,i) in metadata.items" :key="i"><strong>{{ row.address }} · {{ row.content }}</strong><span>{{ row.dataValue }} {{ row.tranferUnit }} · Bereich {{ row.rangeStart }}–{{ row.rangeEnd }}</span></div></div></details>
 </section>
</template>
