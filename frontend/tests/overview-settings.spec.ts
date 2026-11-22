import { createApp, nextTick } from 'vue'
import { expect, it, vi } from 'vitest'
import { api } from '../src/api'
import OverviewSettings from '../src/components/OverviewSettings.vue'
import { defaultOverview } from '../src/overview'

it('selects multiple configured Gira objects independently of their live values', async () => {
  vi.spyOn(api, 'giraOverviewOptions').mockResolvedValue({
    items: [
      { layout_key: 'gira:first', name: 'Leistung', object_key: 'CO@10' },
      { layout_key: 'gira:second', name: '', object_key: 'CO@11' },
    ],
  })
  const save = vi.spyOn(api, 'saveOverview').mockImplementation(async (layout) => layout)
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(OverviewSettings, { layout: defaultOverview, giraRevision: 0 })
  app.mount(host)
  try {
    const option = (description: string) => [...host.querySelectorAll('label')]
      .find(label => label.textContent?.trim() === description)?.querySelector('input')
    await vi.waitFor(() => expect(option('CO@11')).toBeTruthy())
    option('Leistung')!.click()
    option('CO@11')!.click()
    const columns = host.querySelector<HTMLSelectElement>('#overview-columns')!
    columns.value = '7'
    columns.dispatchEvent(new Event('change'))
    await nextTick()
    ;[...host.querySelectorAll('button')].find(button => button.textContent?.includes('Übersicht speichern'))!.click()
    expect(save).toHaveBeenCalledWith({
      ...defaultOverview, desktop_columns: 7,
      desktop: [...defaultOverview.desktop, 'gira:first', 'gira:second'],
    })
  } finally {
    app.unmount()
    host.remove()
    vi.restoreAllMocks()
  }
})
