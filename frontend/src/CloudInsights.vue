<script setup lang="ts">
import {ref} from 'vue'
import HistoryChart from './components/HistoryChart.vue'
import {api} from './api'
withDefaults(defineProps<{admin:boolean;mode?:'history'|'device'}>(),{mode:'device'})
const busy=ref(false),error=ref(''),address=ref('2046'),days=ref(1)
const history=ref<Awaited<ReturnType<typeof api.cloudHistory>>|null>(null)
const ota=ref<Awaited<ReturnType<typeof api.cloudInsight>>|null>(null)
const metadata=ref<Awaited<ReturnType<typeof api.cloudInsight>>|null>(null)
const ai=ref<Awaited<ReturnType<typeof api.cloudInsight>>|null>(null)
const state=(value:boolean|null|undefined)=>value==null?'Unbekannt':value?'Ja':'Nein'
const enums=ref<Record<string,Record<string,string>[]>>({})
async function loadEnum(key:string){
 if(busy.value)return
 busy.value=true;error.value=''
 try{enums.value[key]=(await api.cloudEnum(key)).items}
 catch(e){error.value=e instanceof Error?e.message:'Bedeutungen nicht verfügbar'}
 finally{busy.value=false}
}
async function load(kind:'history'|'ota'|'metadata'|'ai'){
 if(busy.value)return
 busy.value=true;error.value=''
 try{
  if(kind==='history'){
   const end=new Date(),start=new Date(end.getTime()-days.value*86400000)
   const format=(d:Date)=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Etc/GMT-1',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(d)
   const selected = address.value
   history.value=await api.cloudHistory(selected,format(start),format(end),days.value>1?'month':'day')
   historyLabel.value = historyLabels[selected] || 'Messwert'
  }else if(kind==='ota')ota.value=await api.cloudInsight(kind)
  else if(kind==='ai')ai.value=await api.cloudInsight(kind)
  else {metadata.value=await api.cloudInsight(kind);enums.value={}}
 }catch(e){error.value=e instanceof Error?e.message:'Cloud-Abfrage fehlgeschlagen'}
 finally{busy.value=false}
}
const historyLabels: Record<string,string> = {'2046':'Austritt','2045':'Eintritt','2047':'Warmwasser','2048':'Außen','2078+9':'Tages-Stromverbrauch'}
const historyLabel = ref('')
</script>
<template>
 <section class="settings-panel panel">
  <span class="section-caption">PHNIX CLOUD · LESEND</span><h2>{{ mode==='history'?'Historische Messwerte':'Geräteinformationen' }}</h2>
  <p v-if="!admin" class="section-hint">Zum Abrufen als Administrator anmelden.</p>
  <p v-if="error" role="alert" class="read-error">{{ error }}</p>
  <div v-if="mode==='history'" class="cloud-extra-controls">
   <label>Messwert<select v-model="address" class="settings-input"><option value="2046">Vorlauf</option><option value="2045">Rücklauf</option><option value="2047">Warmwasser</option><option value="2048">Außen</option><option value="2078+9">Tages-Stromverbrauch</option></select></label>
   <label>Zeitraum (UTC+1)<select v-model.number="days" class="settings-input"><option :value="1">24 Stunden</option><option :value="7">7 Tage</option><option :value="30">30 Tage</option></select></label>
   <button class="outlined-action" :disabled="busy||!admin" @click="load('history')">Verlauf laden</button>
  </div>
  <p v-if="mode==='history'&&!history" class="section-hint">Messwert und Zeitraum auswählen, dann Verlauf laden. Die historischen Daten stammen aus der Cloud, auch bei ausgewählter Modbus-Verbindung.</p>
  <div v-if="mode==='history'&&history">
   <p class="section-hint">{{ history.points.length }} Messpunkte · {{ history.unit }} · Abfrage {{ new Date(history.checked_at).toLocaleString('de-DE') }} {{ history.cached?'(Cache)':'' }}</p>
   <p v-if="history.points.length" class="section-hint">Wertebereich: {{ Math.min(...history.points.map(p=>p.value)).toLocaleString('de-DE') }}–{{ Math.max(...history.points.map(p=>p.value)).toLocaleString('de-DE') }} {{ history.unit }}</p>
   <HistoryChart v-if="history.points.length" :points="history.points" :label="historyLabel" :unit="history.unit" cloud />
   <p v-if="history.points.some(p=>p.incomplete)" class="section-hint">Der laufende Tag kann unvollständig sein. Ein dort gemeldeter Nullwert ist kein bestätigter Nullverbrauch.</p>
   <p v-if="!history.points.length">Keine Messpunkte im gewählten Zeitraum.</p>
   <details><summary>Messpunkte mit Zeitstempeln</summary><div class="history-points"><div v-for="point in history.points" :key="point.time"><time>{{ point.time }}</time><strong>{{ point.value.toLocaleString('de-DE') }} {{ history.unit }}</strong><span v-if="point.incomplete">Laufender Tag – möglicherweise unvollständig</span></div></div></details>
  </div>
  <div v-if="mode==='device'" class="cloud-extra-controls"><button class="outlined-action" :disabled="busy||!admin" @click="load('ota')">Geräte-Firmware: Verfügbarkeit prüfen</button><button class="outlined-action" :disabled="busy||!admin" @click="load('metadata')">Hersteller-Servicekatalog laden</button><button class="outlined-action" :disabled="busy||!admin" @click="load('ai')">AI- und SG-Unterstützung prüfen</button></div>
  <div v-if="ai" class="timer-time-card"><strong>Herstellerstatus · {{ new Date(ai.checked_at).toLocaleString('de-DE') }}</strong><span>AI-Frequenzregelung unterstützt: {{ state(ai.frequency_supported) }}</span><span>AI-Energiesparen eingeschaltet: {{ state(ai.ai_enabled) }}</span><span>SG-Ready unterstützt: {{ state(ai.sg_supported) }}</span><span>Gemeldeter SG-Modus: {{ ai.sg_mode??'Unbekannt' }}</span><small>Unterstützung bedeutet nicht, dass eine Funktion eingeschaltet ist. Rein lesende Anzeige.</small></div>
  <p v-if="ota" role="status">{{ ota.available?'Firmwareangebot gemeldet ('+ota.count+').':'Kein Firmwareupdate angeboten.' }} Geprüft {{ new Date(ota.checked_at).toLocaleString('de-DE') }}. Es wird kein Update gestartet.</p>
  <details v-if="metadata"><summary>{{ metadata.items?.length||0 }} Hersteller-Einträge</summary><p class="section-hint">{{ metadata.source }}</p><div class="history-points"><div v-for="(row,i) in metadata.items" :key="i"><strong>{{ row.num }} · {{ row.content }} <small>({{ row.address }})</small></strong><span>{{ row.dataValue }} {{ row.tranferUnit }} <template v-if="row.rangeStart||row.rangeEnd">· Bereich {{ row.rangeStart }}–{{ row.rangeEnd }}</template></span><small>{{ row.comparison }}</small><button v-if="row.enum_key" class="outlined-action" :disabled="busy||!admin" @click="loadEnum(row.enum_key)">Bedeutungen laden</button><ul v-if="row.enum_key&&enums[row.enum_key]"><li v-for="(item,n) in enums[row.enum_key]" :key="n">{{ item.value }}: {{ item.enMeaning||item.meaning||item.description }}</li><li v-if="!enums[row.enum_key]?.length">Keine zusätzlichen Bedeutungen gemeldet.</li></ul></div></div></details>
 </section>
</template>
