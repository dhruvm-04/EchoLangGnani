import { chromium } from 'playwright'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const page = await context.newPage()
  await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
  await page.locator('.language-grid button[lang="en"]').click()
  await page.getByRole('button', { name: 'Type instead' }).click()
  await page.getByLabel('Your request').fill('I need a plumber in Nanded')
  await page.getByRole('button', { name: 'Send request' }).click()
  await page.getByRole('button', { name: 'Yes' }).waitFor({ timeout: 45000 })
  await page.getByRole('button', { name: 'Yes' }).click()
  await page.getByRole('button', { name: 'New search' }).waitFor({ timeout: 45000 })
  if (!await page.getByText(/No entries match yet|Listening to \d+ of \d+/).isVisible()) {
    throw new Error('Local directory result state is missing')
  }
  await page.getByRole('button', { name: 'Offer a service' }).click()
  await page.getByRole('button', { name: 'Start my listing' }).waitFor()
  console.log('Live browser flow passed: confirmed search, local results, provider entry point.')
  await context.close()
} finally {
  await browser.close()
}
