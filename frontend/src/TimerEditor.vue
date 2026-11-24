<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {api} from './api'
import type {TransportId} from './api'
const props=defineProps<{transport:TransportId;admin:boolean;silent?:boolean}>()
const kind=ref(props.silent?'silent':'operating')
const values=ref<Record<string,number>>({})
const baseline=ref<Record<string,number>>({})
const invalid=ref(new Set<number>())
const numberDrafts=ref<Record<number,string>>({})
const timeDrafts=ref<Record<number,string>>({})
const busy=ref(false), loaded=ref(false), error=ref(''), message=ref('')
const tab=ref(0)
const days=['Mo','Di','Mi','Do','Fr','Sa','So']
const modes=[['Warmwasser',0],['Heizen',1],['Kühlen',2],['Warmwasser + Heizen',3],['Warmwasser + Kühlen',4],['Modus beibehalten',9]] as const
const base=computed(()=>kind.value==='operating'?1281+tab.value*7:1256+tab.value*2)
const maskReg=computed(()=> (kind.value==='operating'?1323:1268)+Math.floor(tab.value/2))
const shift=computed(()=>8*(tab.value%2))
const ownByte=computed(()=> (values.value[maskReg.value]??0)>>shift.value &255)
let generation=0
async function read(){
  if(busy.value)return
  const request=++generation, transport=props.transport, group=kind.value
  busy.value=true; loaded.value=false; invalid.value.clear(); numberDrafts.value={};timeDrafts.value={}; error.value=''; message.value=''
  try{
    const result=await api.timerRead(group,transport)
    if(request!==generation)return
    values.value={...result.values};baseline.value={...result.values};loaded.value=true
  }catch(e){if(request===generation)error.value=e instanceof Error?e.message:'Lesen fehlgeschlagen'}
  finally{if(request===generation)busy.value=false}
}
async function save(){
  if(!loaded.value || busy.value || (!props.admin || props.transport==='display_modbus') || invalid.value.size)return
  const request=++generation
  busy.value=true;error.value='';message.value=''
  try{
    const result=await api.timerWrite(kind.value,props.transport,{...values.value},{...baseline.value})
    if(request!==generation)return
    if(result.confirmed && result.values){values.value={...result.values};baseline.value={...result.values};message.value=result.status==='unchanged'?'Zeitprogramm bereits so eingestellt.':'Zeitprogramm durch Readback bestätigt.'}
    else {error.value=result.message||'Schreiben nicht bestätigt. Neu lesen.';loaded.value=false}
  }catch(e){if(request===generation){error.value=e instanceof Error?e.message:'Schreiben fehlgeschlagen';loaded.value=false}}
  finally{if(request===generation)busy.value=false}
}
function timeText(reg:number){if(reg in timeDrafts.value)return timeDrafts.value[reg];const v=values.value[reg];if(v==null || v>>8>23 || (v&255)>59)return '';return String(v>>8).padStart(2,'0')+':'+String(v&255).padStart(2,'0')}
function setTime(reg:number,event:Event){const text=(event.target as HTMLInputElement).value;timeDrafts.value[reg]=text;const [h,m]=text.split(':').map(Number);if(Number.isFinite(h)&&Number.isFinite(m)){values.value[reg]=h*256+m;invalid.value.delete(reg)}else invalid.value.add(reg)}
function setOwnBit(bit:number,event:Event){const old=values.value[maskReg.value]??0;const enabled=(event.target as HTMLInputElement).checked;const flag=bit<<shift.value;values.value[maskReg.value]=enabled?old|flag:old&~flag}
function numberInput(reg:number,event:Event){
  const text=(event.target as HTMLInputElement).value, n=Number(text)
  numberDrafts.value[reg]=text
  if(text===''||!Number.isFinite(n)||n < -3276.8||n > 3276.7||Math.abs(n*10-Math.round(n*10))>1e-7){invalid.value.add(reg);return}
  invalid.value.delete(reg);values.value[reg]=Math.round(n*10)&65535
}
function silentTime(start:boolean){const r=start?1245:1248;if(r in timeDrafts.value)return timeDrafts.value[r];return String(values.value[r]??0).padStart(2,'0')+':'+String(values.value[r+1]??0).padStart(2,'0')}
function setSilentTime(start:boolean,event:Event){const text=(event.target as HTMLInputElement).value;const [h,m]=text.split(':').map(Number);const r=start?1245:1248;timeDrafts.value[r]=text;if(Number.isFinite(h)&&Number.isFinite(m)){values.value[r]=h;values.value[r+1]=m;invalid.value.delete(r)}else invalid.value.add(r)}
watch([()=>props.transport,kind],()=>{generation++;busy.value=false;loaded.value=false;values.value={};tab.value=0;void read()})
onMounted(read)
</script>
<template>
  <div class="timer-editor">
    <div v-if="!silent" class="timer-tabs" aria-label="Zeitprogrammtyp">
      <button :disabled="busy" :class="{selected:kind==='operating'}" @click="kind='operating'">Betriebsarten M1–M6</button>
      <button :disabled="busy" :class="{selected:kind==='weekly'}" @click="kind='weekly'">Ein-/Aus-Wochentimer</button>
    </div>
    <p class="section-hint">Quelle: {{ {cloud:'PHNIX Cloud',warmlink_raw:'LTE-/Warmlink-Modbus',standard_modbus:'Standard-Modbus',display_modbus:'Display-Modbus'}[transport] }} · {{ transport === 'display_modbus' ? 'Lesend. Fehlende Timerwerte über die Display-Parametersynchronisation anfordern.' : 'Änderungen werden erst nach Lesen des vollständigen Ausgangszustands freigegeben.' }}</p>
    <p v-if="error" role="alert" class="read-error">{{ error }}</p>
    <p v-if="message" role="status" class="success-text">{{ message }}</p>
    <button type="button" class="outlined-action" :disabled="busy" @click="read">{{ busy?'Bitte warten …':'Werte aktualisieren' }}</button>
    <template v-if="loaded">
      <div v-if="!silent" class="timer-tabs program-tabs"><button v-for="n in 6" :key="n" type="button" :disabled="busy" :class="{selected:tab===n-1}" @click="tab=n-1">{{ kind==='operating'?'M':'' }}{{ n }}</button></div>
      <fieldset :disabled="busy||!admin||transport==='display_modbus'" class="timer-fields">
        <template v-if="silent">
          <div v-for="start in [true,false]" :key="String(start)" class="timer-time-card">
            <label><input type="checkbox" :checked="!!values[start?1244:1247]" @change="values[start?1244:1247]=($event.target as HTMLInputElement).checked?1:0" /> {{ start?'Ruhemodus einschalten':'Ruhemodus ausschalten' }}</label>
            <label>Uhrzeit<input type="time" class="settings-input" :value="silentTime(start)" @input="setSilentTime(start,$event)" required /></label>
          </div>
        </template>
        <template v-else>
          
          <div class="timer-time-card"><label><input type="checkbox" :checked="!!(ownByte&128)" @change="setOwnBit(128,$event)" /> Zeitprogramm aktiv</label>
            <div class="timer-days"><label v-for="(day,i) in days" :key="day"><input type="checkbox" :checked="!!(ownByte&(1<<i))" @change="setOwnBit(1<<i,$event)" />{{ day }}</label></div>
          </div>
          <div class="timer-form-grid">
            <label>Start<input class="settings-input" type="time" :value="timeText(base)" @input="setTime(base,$event)" required /></label>
            <label>Ende<input class="settings-input" type="time" :value="timeText(base+1)" @input="setTime(base+1,$event)" required /></label>
            <template v-if="kind==='operating'">
              <label>Betriebsart<select class="settings-input" v-model.number="values[base+5]"><option v-for="[label,value] in modes" :key="value" :value="value">{{ label }}</option></select></label>
              <label v-for="[label,offset] in [['Warmwasser (°C)',2],['Heizen (°C)',3],['Kühlen (°C)',4],['Max. Leistung (kW)',6]] as const" :key="offset">{{ label }}<input class="settings-input" type="number" step="0.1" :value="numberDrafts[base+offset] ?? ((values[base+offset]??0)>=32768?(values[base+offset]??0)-65536:(values[base+offset]??0))/10" @input="numberInput(base+offset,$event)" /></label>
            </template>
          </div>
        </template>
      </fieldset>
      <p v-if="transport !== 'display_modbus'" class="section-hint">Aktive betroffene Programme werden vor Parameteränderungen deaktiviert und erst nach bestätigten Zwischenwerten wieder freigegeben. Bei Fehlern stoppt der Auftrag.</p>
      <p v-if="invalid.size" class="read-error">Bitte gültige Uhrzeiten und Zahlen in 0,1-Schritten eingeben.</p>
      <button v-if="transport !== 'display_modbus'" class="main-action" :disabled="busy||!admin||invalid.size>0" @click="save">Änderungen mit Readback senden</button>
      <p v-if="!admin && transport !== 'display_modbus'" class="section-hint">Zum Ändern oben rechts als Administrator anmelden.</p>
    </template>
  </div>
</template>
