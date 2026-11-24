import { createApp, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '../src/api'
import CameraDialog from '../src/components/CameraDialog.vue'
import OperationDialog from '../src/components/OperationDialog.vue'

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

it('starts another JPEG request after the configured delay and stops when closed', async () => {
  vi.useFakeTimers()
  const root = document.createElement('div')
  const app = createApp(CameraDialog, { available: true, mode: 'jpeg', interval: 500 })
  const dialog = app.mount(root)
  try {
    dialog.open()
    await nextTick()
    const image = root.querySelector('img')!
    expect(image.getAttribute('src')).toBe('/api/camera/stream?frame=1')
    image.dispatchEvent(new Event('load'))
    await vi.advanceTimersByTimeAsync(499)
    expect(image.getAttribute('src')).toBe('/api/camera/stream?frame=1')
    await vi.advanceTimersByTimeAsync(1)
    expect(image.getAttribute('src')).toBe('/api/camera/stream?frame=2')
    image.dispatchEvent(new Event('load'))
    root.querySelector('button')!.click()
    await nextTick()
    expect(root.querySelector('img')).toBeNull()
    await vi.advanceTimersByTimeAsync(500)
    dialog.open()
    await nextTick()
    expect(root.querySelector('img')?.getAttribute('src')).toBe('/api/camera/stream?frame=3')
  } finally {
    app.unmount()
  }
})

it('writes a standard Modbus operation with a freshly read raw value', async () => {
  const read = vi.spyOn(api, 'read').mockResolvedValue({
    register: 1011,
    value: 'Aus',
    raw: 0,
    transport: 'standard_modbus',
    quality: 'fresh',
    unit: '',
    timestamp: '2026-11-24T09:00:00Z',
  })
  const write = vi
    .spyOn(api, 'writeParameter')
    .mockResolvedValue({ confirmed: true, status: 'confirmed' })
  const root = document.createElement('div')
  const app = createApp(OperationDialog, {
    transport: 'standard_modbus',
    transportLabel: 'Modbus-Standard',
    admin: true,
    canOperate: true,
    cloudRows: [],
  })
  const dialog = app.mount(root)
  try {
    dialog.open('Power')
    await vi.waitFor(() => expect(root.querySelector<HTMLSelectElement>('select')?.value).toBe('0'))
    const select = root.querySelector<HTMLSelectElement>('select')!
    select.value = '1'
    select.dispatchEvent(new Event('change'))
    await nextTick()
    root.querySelector<HTMLButtonElement>('.main-action')!.click()
    await vi.waitFor(() => expect(root.textContent).toContain('Standard-Modbus-Readback bestätigt'))
    expect(read.mock.calls).toEqual([
      [1011, 'standard_modbus'],
      [1011, 'standard_modbus'],
    ])
    expect(write).toHaveBeenCalledWith(1011, 'standard_modbus', '1', '0', 'standard_modbus')
  } finally {
    app.unmount()
  }
})
