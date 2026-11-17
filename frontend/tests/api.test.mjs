import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import {test} from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/api.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.ESNext}}).outputText
const {api, errorMessage, writeValueText} = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'))

test('R02 numeric v-model values can reach the write request', async () => {
  const original = globalThis.fetch
  let body
  globalThis.fetch = async (_url, init) => {
    body = JSON.parse(init.body)
    return new Response(JSON.stringify({status:'confirmed',confirmed:true,code:'R02'}))
  }
  try {
    await api.cloudWrite('R02', writeValueText(35.5), '35')
    assert.equal(body.value, '35.5')
    assert.equal(writeValueText(' 35.5 '), '35.5')
  } finally { globalThis.fetch = original }
})

test('readable string, validation-array and object errors without dumping inputs', () => {
  assert.equal(errorMessage({detail:'Nicht angemeldet'},403), 'Nicht angemeldet')
  assert.equal(errorMessage({detail:[{loc:['body','admin_password'],msg:'Field required',input:'secret'}]},422), 'admin_password: Field required')
  assert.equal(errorMessage({detail:{message:'Abgelehnt'}},409), 'Abgelehnt')
  assert.match(errorMessage({unexpected:{value:'secret'}},502), /HTTP 502/)
  assert.equal(errorMessage({detail:[{msg:'A'},{msg:'B'}]},422), 'A; B')
})

test('GET and POST both format structured failures', async () => {
  const original = globalThis.fetch
  globalThis.fetch = async () => new Response(JSON.stringify({detail:[{msg:'Ungültiger Wert'}]}),{status:422})
  try {
    await assert.rejects(api.health(), /Ungültiger Wert/)
    await assert.rejects(api.cloudAccount(''), /Ungültiger Wert/)
  } finally { globalThis.fetch = original }
})


test('offline POSTs fail before sending and are never queued', async () => {
  const descriptor=Object.getOwnPropertyDescriptor(globalThis,'navigator')
  const originalFetch=globalThis.fetch
  let calls=0
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{onLine:false}})
  globalThis.fetch=async()=>{calls++;return new Response('{}')}
  try {
    await assert.rejects(api.cloudWrite('R02','35.5','35'),/Offline/)
    assert.equal(calls,0)
  } finally {
    globalThis.fetch=originalFetch
    if(descriptor)Object.defineProperty(globalThis,'navigator',descriptor)
    else delete globalThis.navigator
  }
})
