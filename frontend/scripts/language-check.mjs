import { chromium } from 'playwright'
import { mkdir, readFile } from 'node:fs/promises'

const codes = ['bn-IN', 'en-IN', 'gu-IN', 'hi-IN', 'kn-IN', 'ml-IN', 'mr-IN', 'pa-IN', 'ta-IN', 'te-IN']
const translations = Object.fromEntries(await Promise.all(codes.map(async code => [code, JSON.parse(await readFile(new URL(`../src/locales/${code}.json`, import.meta.url), 'utf8'))])))
const keys = Object.keys(translations['en-IN'])
await mkdir('.qa', { recursive: true })
for (const code of codes) {
  if (keys.some(key => !translations[code][key])) throw new Error(`Missing translated UI text for ${code}`)
}

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  for (const code of codes) {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const page = await context.newPage()
    await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
    if (code === 'en-IN') await page.screenshot({ path: '.qa/language-welcome.png', fullPage: true })
    if (await page.locator('.language-grid button').count() !== 10) throw new Error('Language picker does not show ten buttons')
    await page.locator(`.language-grid button[lang="${code.slice(0, 2)}"]`).click()
    if (!await page.getByRole('button', { name: translations[code].findHelp, exact: true }).isVisible()) throw new Error(`Find button is not translated for ${code}`)
    const chosen = await page.evaluate(() => ({ lang: document.documentElement.lang, stored: localStorage.getItem('echolang-language') }))
    if (chosen.lang !== code.slice(0, 2) || chosen.stored !== code) throw new Error(`UI and voice language are not saved for ${code}`)
    const geometry = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, viewport: innerWidth }))
    if (geometry.content > geometry.viewport + 1) throw new Error(`Horizontal overflow in ${code}: ${JSON.stringify(geometry)}`)
    if (code === 'ta-IN') { await page.waitForTimeout(800); await page.screenshot({ path: '.qa/tamil-home.png', fullPage: true }) }
    await page.reload({ waitUntil: 'networkidle' })
    if (await page.locator('.language-grid').count()) throw new Error(`Language picker reappeared for ${code}`)
    await context.close()
  }

  const context = await browser.newContext()
  const page = await context.newPage()
  let startedLanguage = ''
  let resumedLanguage = ''
  let customerLanguage = ''
  await page.route('**/api/turn', route => {
    const body = route.request().postData() || ''
    customerLanguage = body.includes('hi-IN') && body.includes('selected_language') ? 'hi-IN' : ''
    route.fulfill({ json: { transcript: 'मुझे प्लंबर चाहिए', detectedLanguage: 'hi-IN', replyText: 'क्या आपको नांदेड़ में प्लंबर चाहिए?', replyAudioBase64: null, state: { phase: 'awaiting_confirmation', category: 'plumber', location: 'Nanded', language: 'hi-IN', availability: null, preferred_language: null, result_index: 0 }, matches: [], activeIndex: null } })
  })
  await page.route('**/api/providers/start', route => {
    startedLanguage = JSON.parse(route.request().postData()).language
    route.fulfill({ json: { draftId: 'language-draft', fields: {}, phase: 'question', field: 'name', replyText: 'What is your name?', replyAudioBase64: null } })
  })
  await page.route('**/api/providers/drafts/language-draft?*', route => {
    resumedLanguage = new URL(route.request().url()).searchParams.get('selected_language')
    route.fulfill({ json: { draftId: 'language-draft', fields: {}, phase: 'question', field: 'name', replyText: 'உங்கள் பெயர் என்ன?', replyAudioBase64: null } })
  })
  await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
  await page.locator('.language-grid button[lang="hi"]').click()
  await page.getByRole('button', { name: translations['hi-IN'].typeInstead }).click()
  await page.getByLabel(translations['hi-IN'].requestLabel).fill('मुझे प्लंबर चाहिए')
  await page.getByRole('button', { name: translations['hi-IN'].sendRequest }).click()
  await page.getByRole('button', { name: translations['hi-IN'].yes }).waitFor()
  if (customerLanguage !== 'hi-IN') throw new Error('Customer request did not use the selected voice language')
  await page.getByRole('button', { name: translations['hi-IN'].offerService, exact: true }).click()
  await page.getByRole('button', { name: translations['hi-IN'].startListing }).click()
  if (startedLanguage !== 'hi-IN') throw new Error('Provider onboarding did not use the selected voice language')
  await page.locator('.language-switch').click()
  await page.locator('.language-grid button[lang="ta"]').click()
  await page.getByText('உங்கள் பெயர் என்ன?').waitFor()
  if (resumedLanguage !== 'ta-IN') throw new Error('Changing language did not update the provider draft')
  await context.close()
  console.log('All ten UI languages, persistence, and provider language switching passed.')
} finally {
  await browser.close()
}
