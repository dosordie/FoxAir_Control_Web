import { expect, it } from 'vitest'
import { useRegisterFavorites } from '../../src/composables/useRegisterFavorites'

it('persists a selection across instances and removes it again without storing measurements', () => {
  const records = new Map<string,string>()
  const storage = {getItem:(key:string)=>records.get(key)??null,setItem:(key:string,value:string)=>{records.set(key,value)}}
  const first=useRegisterFavorites(storage)
  first.toggleFavorite(1158)
  const reopened=useRegisterFavorites(storage)
  expect(reopened.isFavorite(1158)).toBe(true)
  expect([...records.values()]).toEqual(['[1158]'])
  reopened.toggleFavorite(1158)
  expect(useRegisterFavorites(storage).favoriteIds.value).toEqual([])
})

it('ignores damaged and invalid preference data and tolerates blocked storage', () => {
  const storage={getItem:()=>'{broken',setItem:()=>{throw new Error('blocked')}}
  const state=useRegisterFavorites(storage)
  expect(state.favoriteIds.value).toEqual([])
  state.toggleFavorite(1158)
  expect(state.isFavorite(1158)).toBe(true)
  const invalid=useRegisterFavorites({getItem:()=>'[1158,1158,"1158",-1,100000]',setItem:()=>{}})
  expect(invalid.favoriteIds.value).toEqual([1158])
})
