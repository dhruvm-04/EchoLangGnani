import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const output = new URL('../.qa/', import.meta.url)
await mkdir(output, { recursive: true })
const languages = ['bn-IN','en-IN','gu-IN','hi-IN','kn-IN','ml-IN','mr-IN','pa-IN','ta-IN','te-IN']

async function inspect(viewport, name) {
  const context = await browser.newContext({ viewport })
  const page = await context.newPage()
  await page.addInitScript(() => localStorage.setItem('echolang-intro-seen', '1'))
  await page.route('**/api/config', route => route.fulfill({ json: {
    languages: languages.map(code => ({ code, name: code })), sttModel: 'prisma-v3.0', ttsModel: 'timbre-v2.5',
    requiresLanguageSelection: false, gnaniKeyConfigured: true, reasoningConfigured: true,
  } }))
  await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
  await page.locator('.language-grid button[lang="en"]').click()
  await page.screenshot({ path: fileURLToPath(new URL(`${name}-dark.png`, output)), fullPage: true })
  await page.getByRole('button', { name: 'Use light mode' }).click()
  await page.waitForTimeout(450)
  await page.screenshot({ path: fileURLToPath(new URL(`${name}-light.png`, output)), fullPage: true })
  if (name === 'mobile') {
    let calls = 0
    await page.route('**/api/turn', route => {
      calls += 1
      const done = calls >= 2
      const activeIndex = calls === 3 ? 1 : 0
      route.fulfill({ json: {
        transcript: !done ? 'I need a plumber in Nanded' : calls === 2 ? 'yes' : calls === 3 ? 'next' : 'previous', detectedLanguage: 'en-IN',
        replyText: done ? `${activeIndex + 1} of 2. ${activeIndex ? 'Ravi Plumbing' : 'Asha Repairs'}. Say next, previous, or repeat.` : 'You need a plumber in Nanded. Is that right?',
        replyAudioBase64: null, speechWarning: null,
        state: { phase: done ? 'done' : 'awaiting_confirmation', category: 'plumber', location: 'Nanded', language: 'en-IN', availability: 'weekend', preferred_language: 'Hindi', result_index: activeIndex },
        category: 'plumber', location: 'Nanded',
        activeIndex: done ? activeIndex : null, matches: done ? [
          { id: 'one', name: 'Asha Repairs', services: ['plumber'], area: 'Nanded', delivery: 'home visits', phone: '9876543210', hours: 'weekends', languages: 'Hindi', price: 'quote', status: 'published', updated_at: '2026-11-07' },
          { id: 'two', name: 'Ravi Plumbing', services: ['plumber'], area: 'Nanded', delivery: 'home visits', phone: '9876543211', hours: 'weekends', languages: 'Hindi', price: 'quote', status: 'published', updated_at: '2026-11-07' },
        ] : [],
      } })
    })
    await page.getByRole('button', { name: 'Type instead' }).click()
    await page.getByLabel('Your request').fill('I need a plumber in Nanded')
    await page.getByRole('button', { name: 'Send request' }).click()
    await page.getByRole('button', { name: 'Yes' }).click()
    await page.waitForTimeout(500)
    await page.screenshot({ path: fileURLToPath(new URL('mobile-results.png', output)), fullPage: true })
    if (await page.getByRole('link', { name: 'Call provider' }).count() !== 2) throw new Error('Local provider results missing')
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    if (!await page.locator('.provider-card.active').getByText('Ravi Plumbing').isVisible()) throw new Error('Next provider was not selected')
    await page.getByRole('button', { name: 'Previous', exact: true }).click()
    if (!await page.locator('.provider-card.active').getByText('Asha Repairs').isVisible()) throw new Error('Previous provider was not selected')
    const fields = ['name', 'services', 'area', 'delivery', 'phone', 'hours', 'languages', 'price']
    const answers = ['Asha Repairs', 'fan repair, mixer repair', 'Nanded', 'home visits', '9876543210', 'weekdays', 'Hindi', 'quote']
    const provider = { id: 'mine', name: answers[0], services: answers[1].split(', '), area: answers[2], delivery: answers[3], phone: answers[4], hours: answers[5], languages: answers[6], price: answers[7], status: 'published', updated_at: '2026-11-07' }
    let step = 0
    await page.route('**/api/providers/start', route => route.fulfill({ json: { draftId: 'draft-1', fields: {}, phase: 'question', field: fields[0], replyText: 'What should customers call you or your business?', replyAudioBase64: null } }))
    await page.route('**/api/providers/turn', route => {
      const publish = route.request().postData()?.includes('publish') && step === 8
      if (publish) return route.fulfill({ json: { phase: 'published', provider, ownerToken: 'test-owner', replyText: 'Your listing is live in the local directory.', replyAudioBase64: null } })
      step++
      return route.fulfill({ json: { draftId: 'draft-1', fields: Object.fromEntries(fields.slice(0, step).map((field, i) => [field, answers[i]])), phase: step === 8 ? 'review' : 'question', field: step === 8 ? null : fields[step], transcript: answers[step - 1], replyText: step === 8 ? 'Review your listing.' : `What is your ${fields[step]}?`, replyAudioBase64: null } })
    })
    await page.route('**/api/providers/me', route => route.fulfill({ json: provider }))
    await page.getByRole('button', { name: 'Offer a service' }).click()
    await page.getByRole('button', { name: 'Start my listing' }).click()
    for (const answer of answers) {
      await page.getByLabel('Your answer or update').fill(answer)
      await page.getByRole('button', { name: 'Send answer' }).click()
      await page.waitForTimeout(40)
    }
    await page.screenshot({ path: fileURLToPath(new URL('mobile-provider-review.png', output)), fullPage: true })
    if (!await page.getByRole('button', { name: 'Publish my listing' }).isVisible()) throw new Error('Provider review missing')
    await page.getByRole('button', { name: 'Publish my listing' }).click()
    await page.waitForTimeout(100)
    if (!await page.getByText('Live in the directory').isVisible()) throw new Error('Published listing missing')
  }
  const geometry = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: innerWidth }))
  if (geometry.width > geometry.viewport + 1) throw new Error(`${name} overflows horizontally: ${JSON.stringify(geometry)}`)
  await context.close()
}

try {
  await inspect({ width: 390, height: 844 }, 'mobile')
  await inspect({ width: 320, height: 720 }, 'small-mobile')
  await inspect({ width: 1440, height: 900 }, 'desktop')
  const recoveryContext = await browser.newContext()
  const recoveryPage = await recoveryContext.newPage()
  await recoveryPage.addInitScript(() => localStorage.setItem('echolang-intro-seen', '1'))
  await recoveryPage.route('**/api/providers/me', route => route.fulfill({ json: { id: 'recovered', name: 'Asha', services: ['repair'], area: 'Nanded', delivery: 'home visits', phone: '9876543210', hours: '', languages: '', price: '', status: 'published', updated_at: '2026-11-09' } }))
  await recoveryPage.goto('http://127.0.0.1:5173/#recover=sample-token', { waitUntil: 'networkidle' })
  const recovered = await recoveryPage.evaluate(() => ({ token: localStorage.getItem('echolang-owner-token'), hash: location.hash }))
  if (recovered.token !== 'sample-token' || recovered.hash) throw new Error('Recovery link was not saved and removed from the address bar')
  await recoveryContext.close()
  console.log('Visual checks passed at mobile and desktop sizes.')
} finally { await browser.close() }
