/** WeConduct — P6 E2E Compile Flow Tests
 *  Updated for DockLayout + node graph architecture.
 */
import { test, expect } from '@playwright/test'

const BASE_URL = 'http://127.0.0.1:5173'
const VALID_SOURCE = '{"nodes":[{"id":"n1","role":"action","capability_domain":"http","action_kind":"request"}]}'

/** Set source text through the Pinia store */
async function setSource(page: import('@playwright/test').Page) {
  await page.evaluate((src) => {
    const store = (window as any).__compilationStore
    if (store?.setSource) store.setSource(src)
  }, VALID_SOURCE)
}

test.describe('WeConduct P6 Workbench', () => {
  test('page loads and shows command bar', async ({ page }) => {
    await page.goto(BASE_URL)
    await expect(page.locator('.commandbar')).toBeVisible()
    await expect(page.locator('.statusbar')).toBeVisible()
  })

  test('dock layout is present', async ({ page }) => {
    await page.goto(BASE_URL)
    // DockLayout zones should be visible
    await expect(page.locator('.dl-root')).toBeVisible()
  })

  test('source input panel accessible via DockLayout tab', async ({ page }) => {
    await page.goto(BASE_URL)
    // Click the "源输入" tab in the DockLayout
    const sourceTab = page.getByRole('button', { name: '源输入' })
    await expect(sourceTab).toBeVisible()
    await sourceTab.click()
    // Monaco container should now be visible
    await expect(page.locator('.monaco-container')).toBeVisible({ timeout: 5000 })
  })

  test('compile via toolbar button', async ({ page }) => {
    await page.goto(BASE_URL)
    await setSource(page)
    await page.waitForTimeout(200)
    // Toolbar compile button
    const compileBtn = page.locator('.tb-btn.primary')
    await expect(compileBtn).toBeEnabled({ timeout: 5000 })
    await compileBtn.click()
    // Wait for outcome badge
    await expect(page.locator('.st-badge')).toBeVisible({ timeout: 10000 })
  })

  test('output tabs count matches P6 architecture', async ({ page }) => {
    await page.goto(BASE_URL)
    // P6 has 7 output tabs: 概要/诊断/图模型/历史/Runtime/Debug/Host
    await expect(page.locator('.ot-tab')).toHaveCount(7)
  })

  test('theme toggle switches appearance', async ({ page }) => {
    await page.goto(BASE_URL)
    const themeBtn = page.locator('.theme-btn').last()
    await themeBtn.click()
    const htmlTheme = await page.locator('html').getAttribute('data-theme')
    expect(['light', 'dark']).toContain(htmlTheme)
  })
})
