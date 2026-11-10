import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Check, Headphones, MapPin, Mic, Moon, Pause, Play, RotateCcw, Search, Sun, X, BriefcaseBusiness, Phone, Pencil, ShieldCheck, Globe2 } from 'lucide-react'
import { startRecording, type Recording } from './audio'
import { isLanguageCode, languages, ui, type CopyKey, type LanguageCode } from './i18n'
import { apiFetch, appHome } from './paths'

type Language = { code: string; name: string }
type Conversation = { phase: string; category: string | null; location: string | null; language: string | null; availability: string | null; preferred_language: string | null; result_index: number }
type Provider = { id: string; name: string; services: string[]; area: string; delivery: string; phone: string; hours: string; languages: string; price: string; status: string; updated_at: string }
type Turn = {
  transcript: string; detectedLanguage: string; replyText: string; replyAudioBase64: string | null
  speechWarning: string | null; state: Conversation; category: string | null; location: string | null
  matches: Provider[]; activeIndex: number | null
}
type ProviderTurn = { draftId?: string; fields?: Record<string, string>; phase: 'question' | 'review' | 'published'; field?: string | null; transcript?: string; replyText: string; replyAudioBase64: string | null; provider?: Provider; ownerToken?: string }
type EditProposal = { field: string | null; value: string | null; transcript: string; replyText: string; replyAudioBase64: string | null }
type Config = { languages: Language[]; sttModel: string; ttsModel: string; requiresLanguageSelection: boolean; gnaniKeyConfigured: boolean; reasoningConfigured: boolean }

const emptyState: Conversation = { phase: 'new', category: null, location: null, language: null, availability: null, preferred_language: null, result_index: 0 }
const listingFields = ['name', 'services', 'area', 'delivery', 'phone', 'hours', 'languages', 'price']
const logoUrl = `${import.meta.env.BASE_URL}echolang-logo.svg`

function friendlyError(language: string, code?: string): string {
  const messages: Record<string, CopyKey> = {
    missing_api_key: 'voiceUnavailable', language_selection_required: 'errorChooseLanguage',
    rate_limited: 'errorWait', empty_transcript: 'errorNotHeard', invalid_audio: 'errorRecord',
    audio_length: 'errorTooLong', reasoning_unavailable: 'errorNotUnderstood',
    invalid_reasoning_response: 'errorSayAgain', reasoning_not_configured: 'voiceUnavailable',
    gnani_access_denied: 'voiceUnavailable', draft_not_found: 'errorDraftExpired',
    owner_required: 'errorOwnerLost', invalid_listing: 'errorInvalidListing',
    duplicate_listing: 'errorDuplicate',
  }
  return ui(language, messages[code || ''] || 'errorGeneric')
}

function App() {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => localStorage.getItem('echolang-theme') === 'light' ? 'light' : 'dark')
  const [showSplash, setShowSplash] = useState(true)
  const [config, setConfig] = useState<Config | null>(null)
  const [language, setLanguage] = useState<LanguageCode>(() => {
    const saved = localStorage.getItem('echolang-language') || ''
    return isLanguageCode(saved) ? saved : 'en-IN'
  })
  const [showLanguagePicker, setShowLanguagePicker] = useState(true)
  const [conversation, setConversation] = useState<Conversation>(emptyState)
  const [turn, setTurn] = useState<Turn | null>(null)
  const [heardText, setHeardText] = useState('')
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [placeDraft, setPlaceDraft] = useState('')
  const [placeOverride, setPlaceOverride] = useState('')
  const [showPlace, setShowPlace] = useState(false)
  const [typedText, setTypedText] = useState('')
  const [showType, setShowType] = useState(false)
  const [audioUrl, setAudioUrl] = useState('')
  const [mode, setMode] = useState<'find' | 'offer'>('find')
  const [providerTurn, setProviderTurn] = useState<ProviderTurn | null>(null)
  const [ownerToken, setOwnerToken] = useState(() => {
    const recovery = new URLSearchParams(window.location.hash.slice(1)).get('recover')
    if (recovery) {
      localStorage.setItem('echolang-owner-token', recovery)
      window.history.replaceState(null, '', window.location.pathname)
      return recovery
    }
    return localStorage.getItem('echolang-owner-token') || ''
  })
  const [myListing, setMyListing] = useState<Provider | null>(null)
  const [editProposal, setEditProposal] = useState<EditProposal | null>(null)
  const [providerInput, setProviderInput] = useState('')
  const recorderRef = useRef<Recording | null>(null)
  const timerRef = useRef<number | null>(null)
  const stopRef = useRef<number | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('echolang-theme', theme) }, [theme])
  useEffect(() => { document.documentElement.lang = language.slice(0, 2) }, [language])
  useEffect(() => {
    if (!showSplash) return
    const duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 900 : 4000
    const timer = window.setTimeout(() => setShowSplash(false), duration)
    return () => window.clearTimeout(timer)
  }, [showSplash])
  useEffect(() => {
    apiFetch('/api/config').then(async response => {
      if (!response.ok) throw new Error('offline')
      const value: Config = await response.json()
      setConfig(value)
    }).catch(() => setError(ui(language, 'errorOfflineLater')))
    return () => { if (timerRef.current) window.clearInterval(timerRef.current); if (stopRef.current) window.clearTimeout(stopRef.current) }
  }, [])
  useEffect(() => {
    if (!ownerToken) return
    apiFetch('/api/providers/me', { headers: { Authorization: `Bearer ${ownerToken}` } })
      .then(response => {
        if (response.status === 401) throw new Error('invalid_token')
        if (!response.ok) throw new Error('offline')
        return response.json()
      })
      .then((provider: Provider) => setMyListing(provider))
      .catch((cause: Error) => {
        if (cause.message === 'invalid_token') { localStorage.removeItem('echolang-owner-token'); setOwnerToken(''); setMyListing(null) }
        else setError(ui(language, 'errorSavedAccess'))
      })
  }, [ownerToken])
  useEffect(() => {
    if (showLanguagePicker) return
    const draftId = localStorage.getItem('echolang-provider-draft')
    if (!draftId) return
    apiFetch(`/api/providers/drafts/${encodeURIComponent(draftId)}?selected_language=${encodeURIComponent(language)}`)
      .then(response => {
        if (response.status === 404) throw new Error('expired_draft')
        if (!response.ok) throw new Error('offline')
        return response.json()
      })
      .then((draft: ProviderTurn) => { setProviderTurn(draft); playReply(draft) })
      .catch((cause: Error) => {
        if (cause.message === 'expired_draft') localStorage.removeItem('echolang-provider-draft')
        else setError(ui(language, 'errorSavedDraft'))
      })
  }, [language, showLanguagePicker])

  function playReply(result: { replyAudioBase64: string | null }) {
    if (!result.replyAudioBase64) { setAudioUrl(''); return }
    const url = `data:audio/wav;base64,${result.replyAudioBase64}`
    setAudioUrl(url)
    window.setTimeout(() => { if (audioRef.current) { audioRef.current.src = url; audioRef.current.play().catch(() => {}) } }, 80)
  }

  async function startProvider() {
    setBusy(true); setError(''); setProviderTurn(null); setEditProposal(null)
    try {
      const response = await apiFetch('/api/providers/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ language }) })
      const data = await response.json()
      if (!response.ok) { setError(friendlyError(language, data.error)); return }
      setProviderTurn(data as ProviderTurn); localStorage.setItem('echolang-provider-draft', data.draftId); playReply(data)
    } catch { setError(ui(language, 'errorOffline')) }
    finally { setBusy(false) }
  }

  async function sendProvider(input: Blob | string, isControl = false) {
    if (!providerTurn?.draftId) return
    setBusy(true); setError('')
    try {
      const form = new FormData()
      form.append('draft_id', providerTurn.draftId)
      form.append('selected_language', language)
      if (typeof input === 'string') form.append(isControl ? 'control' : 'text', input)
      else form.append('audio', input, 'answer.wav')
      const response = await apiFetch('/api/providers/turn', { method: 'POST', body: form })
      const data = await response.json()
      if (!response.ok) { setError(friendlyError(language, data.error)); return }
      const result = data as ProviderTurn
      setProviderTurn(result)
      if (result.transcript && !isControl) setHeardText(result.transcript)
      playReply(result)
      if (result.ownerToken) {
        localStorage.removeItem('echolang-provider-draft')
        localStorage.setItem('echolang-owner-token', result.ownerToken)
        setOwnerToken(result.ownerToken)
        setMyListing(result.provider || null)
      }
    } catch { setError(ui(language, 'errorOffline')) }
    finally { setBusy(false) }
  }

  async function prepareEdit(input: Blob | string) {
    setBusy(true); setError('')
    try {
      const form = new FormData()
      form.append('selected_language', language)
      if (typeof input === 'string') form.append('text', input)
      else form.append('audio', input, 'edit.wav')
      const response = await apiFetch('/api/providers/edit/prepare', { method: 'POST', headers: { Authorization: `Bearer ${ownerToken}` }, body: form })
      const data = await response.json()
      if (!response.ok) { setError(friendlyError(language, data.error)); return }
      setEditProposal(data as EditProposal); setHeardText(data.transcript); playReply(data)
    } catch { setError(ui(language, 'errorOffline')) }
    finally { setBusy(false) }
  }

  async function confirmEdit() {
    if (!editProposal?.field || !editProposal.value) return
    setBusy(true); setError('')
    try {
      const response = await apiFetch('/api/providers/edit/confirm', { method: 'POST', headers: { Authorization: `Bearer ${ownerToken}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ field: editProposal.field, value: editProposal.value, language }) })
      const data = await response.json()
      if (!response.ok) { setError(friendlyError(language, data.error)); return }
      setMyListing(data.provider); setEditProposal(null); playReply(data)
    } catch { setError(ui(language, 'errorOffline')) }
    finally { setBusy(false) }
  }

  async function answerEdit(input: Blob | string) {
    if (!editProposal?.field || !editProposal.value) return
    setBusy(true); setError('')
    try {
      const form = new FormData()
      form.append('field', editProposal.field); form.append('value', editProposal.value)
      form.append('selected_language', language)
      if (typeof input === 'string') form.append('text', input)
      else form.append('audio', input, 'answer.wav')
      const response = await apiFetch('/api/providers/edit/answer', { method: 'POST', headers: { Authorization: `Bearer ${ownerToken}` }, body: form })
      const data = await response.json()
      if (!response.ok) { setError(friendlyError(language, data.error)); return }
      setHeardText(data.transcript); playReply(data)
      if (data.saved) { setMyListing(data.provider); setEditProposal(null) }
      if (data.cancelled) setEditProposal(null)
    } catch { setError(ui(language, 'errorOffline')) }
    finally { setBusy(false) }
  }

  async function sendTurn(input: Blob | string, isControl = false) {
    setBusy(true); setError('')
    try {
      const form = new FormData()
      if (typeof input === 'string') form.append(isControl ? 'control' : 'text', input)
      else form.append('audio', input, 'request.wav')
      form.append('state', JSON.stringify(conversation))
      form.append('selected_language', language)
      if (placeOverride.trim()) form.append('location_override', placeOverride.trim())
      const response = await apiFetch('/api/turn', { method: 'POST', body: form })
      const data = await response.json()
      if (!response.ok) {
        setError(friendlyError(language, data.error)); return
      }
      const result = data as Turn
      setTurn(result)
      if (!isControl) setHeardText(result.transcript)
      setConversation(result.state)
      if (result.state.location) { setPlaceOverride(result.state.location); setPlaceDraft(result.state.location) }
      playReply(result)
    } catch { setError(ui(language, 'errorOffline')) }
    finally { setBusy(false) }
  }

  async function stopRecording() {
    if (!recorderRef.current) return
    const recorder = recorderRef.current
    recorderRef.current = null
    if (timerRef.current) window.clearInterval(timerRef.current)
    if (stopRef.current) window.clearTimeout(stopRef.current)
    setRecording(false)
    try {
      const blob = await recorder.stop()
      if (mode === 'offer') {
        if (editProposal?.field) await answerEdit(blob)
        else if (providerTurn?.draftId && providerTurn.phase !== 'published') await sendProvider(blob)
        else if (myListing) await prepareEdit(blob)
      } else await sendTurn(blob)
    }
    catch { setError(ui(language, 'errorRecord')) }
  }

  async function toggleRecording() {
    if (recording) { await stopRecording(); return }
    if (busy) return
    if (showLanguagePicker) { setError(ui(language, 'errorChooseLanguage')); return }
    setError(''); if (mode === 'find') setTurn(null); setAudioUrl(''); setSeconds(0)
    try {
      recorderRef.current = await startRecording()
      setRecording(true)
      timerRef.current = window.setInterval(() => setSeconds(value => value + 1), 1000)
      stopRef.current = window.setTimeout(() => { void stopRecording() }, 25000)
    } catch { setError(ui(language, 'errorMicrophone')) }
  }

  function savePlace() {
    const place = placeDraft.trim()
    setPlaceOverride(place)
    setConversation(value => ({ ...value, location: place || null }))
    setShowPlace(false)
  }

  function sayPlace() {
    if (!conversation.category) return
    setConversation(value => ({ ...value, phase: 'awaiting_location' }))
    setTurn(null); setHeardText(''); setAudioUrl(''); setError('')
  }

  function reset() {
    setConversation({ ...emptyState, location: placeOverride || null })
    setTurn(null); setHeardText(''); setError(''); setAudioUrl('')
  }

  async function reportProvider(provider: Provider) {
    try {
      const response = await apiFetch(`/api/directory/${provider.id}/report`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason: 'Wrong number or unavailable' }) })
      if (!response.ok) throw new Error('report failed')
      setNotice(ui(language, 'noticeReport'))
    } catch { setError(ui(language, 'errorReport')) }
  }

  async function changeListingStatus(status: 'published' | 'paused') {
    setBusy(true); setError(''); setNotice('')
    try {
      const response = await apiFetch('/api/providers/me/status', { method: 'POST', headers: { Authorization: `Bearer ${ownerToken}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) })
      const data = await response.json()
      if (!response.ok) { setError(friendlyError(language, data.error)); return }
      setMyListing(data)
      setNotice(ui(language, status === 'paused' ? 'noticePaused' : 'noticeLive'))
    } catch { setError(ui(language, 'errorOffline')) }
    finally { setBusy(false) }
  }

  async function deleteListing() {
    if (!window.confirm(ui(language, 'confirmDelete'))) return
    setBusy(true); setError('')
    try {
      const response = await apiFetch('/api/providers/me/delete', { method: 'POST', headers: { Authorization: `Bearer ${ownerToken}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ confirmation: 'delete' }) })
      if (!response.ok) { setError(ui(language, 'errorDelete')); return }
      localStorage.removeItem('echolang-owner-token'); setOwnerToken(''); setMyListing(null); setProviderTurn(null); setEditProposal(null)
      setNotice(ui(language, 'noticeDeleted'))
    } catch { setError(ui(language, 'errorOffline')) }
    finally { setBusy(false) }
  }

  function switchMode(next: 'find' | 'offer') {
    if (recording || busy) return
    setMode(next); setError(''); setNotice(''); setHeardText(''); setAudioUrl('')
  }

  function chooseLanguage(next: LanguageCode) {
    if (recording || busy) return
    setLanguage(next)
    localStorage.setItem('echolang-language', next)
    setShowLanguagePicker(false)
    setConversation({ ...emptyState, location: placeOverride || null })
    setTurn(null); setHeardText(''); setAudioUrl(''); setError(''); setNotice('')
  }

  const voiceReady = Boolean(config?.gnaniKeyConfigured && config?.reasoningConfigured && window.isSecureContext && navigator.mediaDevices?.getUserMedia)
  useEffect(() => { if (config && !voiceReady) setShowType(true) }, [config, voiceReady])
  const status = ui(language, !config ? 'connecting' : !voiceReady ? 'voiceOffline' : recording ? 'listening' : busy ? 'pleaseWait' : mode === 'offer' ? 'offerService' : turn?.state.phase === 'done' ? 'searchReady' : 'readyToListen')
  const flowGuidance = mode === 'offer' ? (editProposal?.replyText || (providerTurn?.phase === 'published' ? '' : providerTurn?.replyText) || (myListing ? ui(language, 'editGuide') : ui(language, 'startGuide'))) : turn?.replyText || ui(language, conversation.phase === 'awaiting_location' ? 'speakPlace' : 'speakNeed')
  const textGuidance = editProposal?.replyText || (providerTurn?.phase === 'published' ? '' : providerTurn?.replyText) || (mode === 'find' ? turn?.replyText : '') || ui(language, 'typeInstead')
  const guidance = !config ? ui(language, 'oneMoment') : !config.reasoningConfigured ? ui(language, 'voiceUnavailable') : recording ? ui(language, 'speakStop') : busy ? ui(language, 'pleaseWait') : voiceReady ? flowGuidance : textGuidance
  const locationLabel = placeOverride || conversation.location || ui(language, 'placeNeeded')
  const compactVoice = (mode === 'find' && ['awaiting_confirmation', 'done'].includes(turn?.state.phase || '')) || (mode === 'offer' && (providerTurn?.phase === 'review' || Boolean(myListing && (!providerTurn || providerTurn.phase === 'published'))))

  useEffect(() => {
    if (mode !== 'find' || turn?.state.phase !== 'done' || turn.activeIndex === null) return
    document.getElementById(`provider-${turn.activeIndex}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [mode, turn?.activeIndex, turn?.state.phase])

  if (new URLSearchParams(window.location.search).has('operator')) return <OperatorPanel />

  if (showSplash) return <div className="splash" aria-label="EchoLang introduction">
    <div className="splash-content">
      <div className="splash-emblem" aria-hidden="true"><img src={logoUrl} alt="" /></div>
      <p className="splash-kicker">A LOCAL SERVICES DIRECTORY</p>
      <div className="splash-wordmark">echo<span>lang.</span></div>
      <h1>Every neighbourhood<br /><em>has a voice.</em></h1>
      <div className="splash-languages" aria-hidden="true">{languages.map(item => <span key={item.code} lang={item.code.slice(0, 2)}>{item.native}</span>)}</div>
    </div>
    <div className="splash-progress" aria-hidden="true"><span /></div>
  </div>

  if (showLanguagePicker) return <div className="app-shell language-welcome">
    <header className="topbar"><a className="brand" href={appHome} aria-label="EchoLang home"><img className="brand-mark" src={logoUrl} alt="" /><span>echo<span className="brand-light">lang.</span></span></a></header>
    <main className="language-page">
      <div className="language-intro"><Globe2 size={30} aria-hidden="true" /><p className="eyebrow">ECHOLANG</p><h1>{ui(language, 'languageTitle')}</h1><p>{ui(language, 'languageIntro')}</p><small>{ui(language, 'languageHint')}</small></div>
      <div className="language-grid" role="group" aria-label="Choose the language for the app and voice">
        {languages.filter(item => !config || config.languages.some(available => available.code === item.code)).map(item =>
          <button type="button" key={item.code} lang={item.code.slice(0, 2)} onClick={() => chooseLanguage(item.code)}>
            <span>{item.native}</span><small>{item.english}</small><ArrowRight size={19} aria-hidden="true" />
          </button>)}
      </div>
    </main>
  </div>

  return <div className="app-shell">
    <header className="topbar">
      <a className="brand" href={appHome} aria-label="EchoLang home" onClick={event => { event.preventDefault(); reset() }}>
        <img className="brand-mark" src={logoUrl} alt="" /><span>echo<span className="brand-light">lang.</span></span>
      </a>
      <div className="top-actions">
        <button className="language-switch" type="button" disabled={recording || busy} onClick={() => setShowLanguagePicker(true)} aria-label={ui(language, 'changeLanguage')}><Globe2 size={17} aria-hidden="true" /> {languages.find(item => item.code === language)?.native}</button>
        <span className="status-pill"><span className={`status-dot ${voiceReady ? '' : 'offline'}`} /> {status}</span>
        <button className="icon-button" type="button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label={ui(language, theme === 'dark' ? 'lightMode' : 'darkMode')} title={ui(language, theme === 'dark' ? 'lightMode' : 'darkMode')}>
          {theme === 'dark' ? <Sun size={20} strokeWidth={1.8} /> : <Moon size={20} strokeWidth={1.8} />}
        </button>
      </div>
    </header>

    <main className="main-grid">
      <section className="intro" aria-labelledby="main-title">
        <p className="eyebrow"><span className="eyebrow-line" /> {ui(language, 'eyebrow')}</p>
        <h1 id="main-title"><em>{ui(language, mode === 'find' ? 'findTitle' : 'offerTitle')}</em></h1>
        {(!config || voiceReady || mode === 'offer') && <p className="intro-copy">{ui(language, mode === 'find' ? 'findIntro' : !voiceReady ? 'offerBegin' : 'offerIntro')}</p>}
        <div className="intro-footer"><span className="tiny-star">✳</span><span>{ui(language, 'tagline')}</span></div>
      </section>

      <section className={`voice-panel ${!voiceReady ? 'text-first' : ''} ${compactVoice ? 'is-followup' : ''}`} aria-label={ui(language, mode === 'find' ? 'findHelp' : 'offerService')}>
        <div className="mode-switch" role="group" aria-label={ui(language, 'chooseAction')}>
          <button type="button" className={mode === 'find' ? 'active' : ''} onClick={() => switchMode('find')}><Search size={17} /> {ui(language, 'findHelp')}</button>
          <button type="button" className={mode === 'offer' ? 'active' : ''} onClick={() => switchMode('offer')}><BriefcaseBusiness size={17} /> {ui(language, 'offerService')}</button>
        </div>
        <div className="panel-head"><span>01 / {ui(language, mode === 'find' ? 'yourRequest' : 'yourListing')}</span><span className="panel-index">ECHOLANG</span></div>
        <div className="voice-center">
          <div className={`orb-frame ${recording ? 'is-recording' : ''} ${busy ? 'is-busy' : ''}`}>
            <span className="orbit orbit-one" /><span className="orbit orbit-two" />
            <button className="record-button" type="button" disabled={busy || !voiceReady || (mode === 'offer' && providerTurn?.phase === 'published' && !myListing)} onClick={() => { if (mode === 'offer' && !providerTurn?.draftId && !myListing) void startProvider(); else void toggleRecording() }} aria-label={ui(language, mode === 'offer' && !providerTurn?.draftId && !myListing ? 'startListing' : recording ? 'stopRecording' : 'startRecording')}>
              {recording ? <Pause size={34} fill="currentColor" strokeWidth={1.5} /> : <Mic size={38} strokeWidth={1.7} />}
            </button>
          </div>
          <p className="voice-status">{recording ? `${ui(language, 'listening')} · ${seconds}s / 25s` : busy ? ui(language, 'oneMoment') : mode === 'offer' && !providerTurn && !myListing ? ui(language, 'startBelow') : ui(language, 'tapToSpeak')}</p>
          <p className="guidance" aria-live="polite">{guidance}</p>
        </div>

        {error && <div className="notice error" role="alert"><X size={17} /> <span>{error}</span></div>}
        {notice && <div className="notice success" role="status"><Check size={17} /> <span>{notice}</span></div>}
        {heardText && !(mode === 'find' && turn?.state.phase === 'done') && !(mode === 'offer' && providerTurn?.phase === 'review') && <div className="heard"><span>{ui(language, 'youSaid')}</span><p>{heardText}</p></div>}
        {mode === 'find' && turn?.state.phase === 'awaiting_confirmation' && <div className="confirm-actions">
          <button type="button" className="button-primary" disabled={busy} onClick={() => void sendTurn('yes', true)}><Check size={19} /> {ui(language, 'yes')}</button>
          <button type="button" className="button-quiet" disabled={busy} onClick={() => void sendTurn('no', true)}><RotateCcw size={18} /> {ui(language, 'changeNeed')}</button>
          <button type="button" className="button-quiet" disabled={busy} onClick={sayPlace}><MapPin size={18} /> {ui(language, 'changePlace')}</button>
        </div>}
        {(voiceReady || showType) && <div className="quick-input">
          {voiceReady && <button className="type-toggle" type="button" onClick={() => setShowType(!showType)}>{ui(language, showType ? 'hideText' : 'typeInstead')} <ArrowRight size={15} /></button>}
          {showType && mode === 'find' && <form className="type-form" onSubmit={event => { event.preventDefault(); if (typedText.trim() && !busy && config?.reasoningConfigured) { void sendTurn(typedText.trim()); setTypedText('') } }}><label htmlFor="type-input">{ui(language, 'requestLabel')}</label><div><input id="type-input" value={typedText} disabled={!config?.reasoningConfigured} onChange={event => setTypedText(event.target.value)} placeholder={ui(language, 'requestPlaceholder')} /><button type="submit" disabled={busy || !config?.reasoningConfigured || !typedText.trim()} aria-label={ui(language, 'sendRequest')}><ArrowRight size={19} /></button></div></form>}
          {showType && mode === 'offer' && (providerTurn?.draftId || myListing) && <form className="type-form" onSubmit={event => { event.preventDefault(); if (!providerInput.trim() || busy || !config?.reasoningConfigured) return; if (editProposal?.field) void answerEdit(providerInput.trim()); else if (providerTurn?.draftId && providerTurn.phase !== 'published') void sendProvider(providerInput.trim()); else if (myListing) void prepareEdit(providerInput.trim()); setProviderInput('') }}><label htmlFor="provider-input">{ui(language, 'answerLabel')}</label><div><input id="provider-input" value={providerInput} disabled={!config?.reasoningConfigured} onChange={event => setProviderInput(event.target.value)} placeholder={ui(language, 'answerPlaceholder')} /><button type="submit" disabled={busy || !config?.reasoningConfigured || !providerInput.trim()} aria-label={ui(language, 'sendAnswer')}><ArrowRight size={19} /></button></div></form>}
        </div>}
        {audioUrl && <button className="listen-again" type="button" onClick={() => { if (audioRef.current) { audioRef.current.currentTime = 0; audioRef.current.play().catch(() => {}) } }}><Play size={16} fill="currentColor" /> {ui(language, 'hearAgain')}</button>}
        <audio ref={audioRef} hidden />

        {mode === 'find' && turn?.state.phase === 'done' && <div className={`results ${turn.matches?.length ? '' : 'no-matches'}`} aria-label={ui(language, 'findResults')}>
          <div className="results-heading"><span>02 / {ui(language, 'findResults')}</span><Search size={18} /></div>
          {(turn.state.availability || turn.state.preferred_language) && <div className="filter-summary">{turn.state.availability && <span>{ui(language, 'when')}: {turn.state.availability}</span>}{turn.state.preferred_language && <span>{ui(language, 'speaks')}: {turn.state.preferred_language}</span>}</div>}
          {!turn.matches?.length && <p>{ui(language, 'noMatches')}</p>}
          {(turn.matches || []).map((provider, index) => <article className={`provider-card ${index === turn.activeIndex ? 'active' : ''}`} id={`provider-${index}`} key={provider.id} aria-current={index === turn.activeIndex ? 'true' : undefined}>
            <strong>{provider.name}</strong><span>{provider.services.join(' · ')}</span>
            <small>{provider.area} · {provider.delivery}{provider.hours ? ` · ${provider.hours}` : ''}{provider.languages ? ` · ${provider.languages}` : ''}</small>
            <div>{provider.id.startsWith('demo-') ? <button type="button" className="demo-call" disabled><Phone size={16} /> {ui(language, 'demoNoCall')}</button> : <><a href={`tel:${provider.phone}`} onClick={() => { void apiFetch(`/api/directory/${provider.id}/contact`, { method: 'POST', keepalive: true }).catch(() => {}) }}><Phone size={16} /> {ui(language, 'callProvider')}</a><button type="button" onClick={() => void reportProvider(provider)}>{ui(language, 'reportIssue')}</button></>}</div>
          </article>)}
          {turn.matches?.length > 0 && <div className="browse-actions"><button type="button" disabled={busy || (turn.activeIndex ?? 0) <= 0} onClick={() => void sendTurn('previous', true)}>{ui(language, 'previous')}</button><button type="button" disabled={busy} onClick={() => void sendTurn('repeat', true)}>{ui(language, 'repeat')}</button><button type="button" disabled={busy || (turn.activeIndex ?? 0) >= turn.matches.length - 1} onClick={() => void sendTurn('next', true)}>{ui(language, 'next')}</button></div>}
          <button className="new-search" type="button" onClick={reset}><RotateCcw size={16} /> {ui(language, 'newSearch')}</button>
        </div>}

        {mode === 'offer' && !providerTurn && !myListing && <div className="offer-actions"><p>{ui(language, 'offerBegin')}</p><button type="button" className="result-main" disabled={busy || !config?.reasoningConfigured} onClick={() => void startProvider()}>{ui(language, 'startListing')} <ArrowRight size={19} /></button></div>}
        {mode === 'offer' && providerTurn?.phase === 'question' && <div className="offer-actions">
          <div className="results-heading"><span>{ui(language, 'detail', { index: Math.max(1, listingFields.indexOf(providerTurn.field || '') + 1) })}</span><Pencil size={16} /></div>
          <p>{ui(language, voiceReady ? 'answerHint' : 'answerLabel')}</p>
          {providerTurn.field && !['name','services','area','delivery','phone'].includes(providerTurn.field) && <button type="button" className="button-quiet offer-skip" disabled={busy} onClick={() => void sendProvider('skip', true)}>{ui(language, 'skipDetail')}</button>}
        </div>}
        {mode === 'offer' && providerTurn?.phase === 'review' && <div className="offer-actions">
          <div className="results-heading"><span>{ui(language, 'reviewListing')}</span><ShieldCheck size={16} /></div>
          <dl className="listing-details">{Object.entries(providerTurn.fields || {}).filter(([field, value]) => listingFields.includes(field) && value).map(([field, value]) => <div className="listing-review-row" key={field}><dt>{ui(language, field as CopyKey)}</dt><dd>{value}</dd><button type="button" className="field-change" disabled={busy} onClick={() => void sendProvider(`change:${field}`, true)} aria-label={`${ui(language, 'change')} ${ui(language, field as CopyKey)}`}>{ui(language, 'change')}</button></div>)}</dl>
          <p>{ui(language, 'reviewPrivacy')}</p>
          {!voiceReady && <p>{ui(language, 'typeInstead')}</p>}
          <button type="button" className="result-main" disabled={busy} onClick={() => void sendProvider('publish', true)}>{ui(language, 'publishListing')} <Check size={19} /></button>
        </div>}
        {mode === 'offer' && myListing && (!providerTurn || providerTurn.phase === 'published') && <div className="offer-actions">
          <div className="results-heading"><span>{ui(language, 'listingTitle')}</span><BriefcaseBusiness size={16} /></div>
          <p className="listing-status">{ui(language, myListing.status === 'published' ? 'liveStatus' : myListing.status === 'paused' ? 'pausedStatus' : myListing.status === 'hidden' ? 'hiddenStatus' : 'pendingStatus')}</p>
          <dl className="listing-details">{Object.entries({ name: myListing.name, services: myListing.services.join(', '), area: myListing.area, delivery: myListing.delivery, phone: myListing.phone, hours: myListing.hours, languages: myListing.languages, price: myListing.price }).filter(([, value]) => value).map(([field, value]) => <div key={field}><dt>{ui(language, field as CopyKey)}</dt><dd>{value}</dd></div>)}</dl>
          <p>{ui(language, voiceReady ? 'updateHint' : 'typeInstead')}</p>
          <div className="listing-controls">
            {myListing.status === 'published' && <button type="button" disabled={busy} onClick={() => void changeListingStatus('paused')}>{ui(language, 'pauseListing')}</button>}
            {myListing.status === 'paused' && <button type="button" disabled={busy} onClick={() => void changeListingStatus('published')}>{ui(language, 'showAgain')}</button>}
            <button type="button" disabled={busy} onClick={() => void deleteListing()}>{ui(language, 'deleteListing')}</button>
          </div>
          {editProposal?.field && editProposal.value && <div className="edit-confirm"><strong>{ui(language, 'changeProposal', { field: ui(language, editProposal.field as CopyKey), value: editProposal.value })}</strong><div><button type="button" className="button-primary" disabled={busy} onClick={() => void confirmEdit()}><Check size={17} /> {ui(language, 'saveChange')}</button><button type="button" className="button-quiet" onClick={() => setEditProposal(null)}>{ui(language, 'cancel')}</button></div></div>}
        </div>}

        <div className="panel-bottom">
          <div className="setting-row">
            <div className="setting-icon"><Headphones size={18} /></div>
            <span>{ui(language, 'language')}</span>
            <strong className="place-value">{languages.find(item => item.code === language)?.native}</strong>
            <button type="button" className="text-link" disabled={busy || recording} onClick={() => setShowLanguagePicker(true)}>{ui(language, 'change')}</button>
          </div>
          {mode === 'find' && <div className="setting-row">
            <div className="setting-icon"><MapPin size={18} /></div>
            <span>{ui(language, 'place')}</span><strong className="place-value">{locationLabel}</strong>
            <button type="button" className="text-link" onClick={() => { setPlaceDraft(placeOverride); setShowPlace(!showPlace) }}>{ui(language, 'change')}</button>
          </div>}
          {mode === 'find' && showPlace && <div className="place-editor"><label htmlFor="place-input">{ui(language, 'cityLabel')}</label><div><input id="place-input" value={placeDraft} onChange={event => setPlaceDraft(event.target.value)} placeholder={ui(language, 'placePlaceholder')} /><button type="button" onClick={savePlace}>{ui(language, 'save')}</button></div></div>}
        </div>
      </section>
    </main>
    <footer className="footer"><span>{ui(language, 'footerLocal')}</span><span>{ui(language, 'voiceBy')}</span></footer>
  </div>
}

export default App

type Report = { id: number; provider_id: string; name: string; phone: string; status: string; reason: string; created_at: string }

function OperatorPanel() {
  const [key, setKey] = useState('')
  const [providers, setProviders] = useState<Provider[]>([])
  const [reports, setReports] = useState<Report[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [recoveryLink, setRecoveryLink] = useState('')
  const [lookupPhone, setLookupPhone] = useState('')
  const [lookupResults, setLookupResults] = useState<Provider[]>([])
  const [metrics, setMetrics] = useState<Record<string, number> | null>(null)

  async function load() {
    setBusy(true); setError(''); setNotice('')
    try {
      const headers = { 'X-Admin-Key': key }
      const [pendingResponse, reportsResponse, metricsResponse] = await Promise.all([
        apiFetch('/api/admin/pending', { headers }), apiFetch('/api/admin/reports', { headers }), apiFetch('/api/admin/metrics', { headers }),
      ])
      if (!pendingResponse.ok || !reportsResponse.ok || !metricsResponse.ok) { setError('Check the operator key and try again.'); return }
      setProviders((await pendingResponse.json()).providers)
      setReports((await reportsResponse.json()).reports)
      setMetrics((await metricsResponse.json()).counts)
      setNotice('Directory review is up to date.')
    } catch { setError('The directory is offline.') }
    finally { setBusy(false) }
  }

  async function decideStatus(provider: Provider, status: 'published' | 'rejected') {
    setBusy(true); setError('')
    try {
      const response = await apiFetch(`/api/admin/providers/${provider.id}/status`, { method: 'POST', headers: { 'X-Admin-Key': key, 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) })
      if (!response.ok) { setError('Could not update this entry.'); return }
      setProviders(items => items.filter(item => item.id !== provider.id))
      setNotice(status === 'published' ? 'Entry approved.' : 'Entry rejected.')
    } catch { setError('The directory is offline.') }
    finally { setBusy(false) }
  }

  async function resolveReport(report: Report, resolution: 'checked' | 'hidden') {
    setBusy(true); setError('')
    try {
      const response = await apiFetch(`/api/admin/reports/${report.id}/resolve`, { method: 'POST', headers: { 'X-Admin-Key': key, 'Content-Type': 'application/json' }, body: JSON.stringify({ resolution }) })
      if (!response.ok) { setError('Could not resolve this report.'); return }
      setReports(items => items.filter(item => item.id !== report.id))
      setNotice(resolution === 'hidden' ? 'Listing hidden and report resolved.' : 'Report marked as checked.')
    } catch { setError('The directory is offline.') }
    finally { setBusy(false) }
  }

  async function recoverProvider(providerId: string) {
    if (!window.confirm('Only continue after you have called the listed number and confirmed the provider wants access on a new device. This will revoke access on the old device.')) return
    setBusy(true); setError(''); setRecoveryLink('')
    try {
      const response = await apiFetch(`/api/admin/providers/${providerId}/recover`, { method: 'POST', headers: { 'X-Admin-Key': key } })
      if (!response.ok) { setError('Could not create a recovery link.'); return }
      const data: { ownerToken: string } = await response.json()
      setRecoveryLink(`${window.location.origin}${appHome}#recover=${encodeURIComponent(data.ownerToken)}`)
    } catch { setError('The directory is offline.') }
    finally { setBusy(false) }
  }

  async function lookupProvider() {
    setBusy(true); setError(''); setLookupResults([])
    try {
      const response = await apiFetch(`/api/admin/providers/by-phone?phone=${encodeURIComponent(lookupPhone)}`, { headers: { 'X-Admin-Key': key } })
      if (!response.ok) { setError('Check the operator key and phone number.'); return }
      setLookupResults((await response.json()).providers)
    } catch { setError('The directory is offline.') }
    finally { setBusy(false) }
  }

  return <div className="app-shell"><header className="topbar"><a className="brand" href={appHome}><img className="brand-mark" src={logoUrl} alt="" /><span>echo<span className="brand-light">lang.</span></span></a><span className="status-pill">Directory review</span></header>
    <main className="operator-page"><h1>Directory <em>review.</em></h1><p>Review new entries and customer reports.</p>
      <form onSubmit={event => { event.preventDefault(); void load() }}><label htmlFor="operator-key">Operator key</label><div><input id="operator-key" type="password" value={key} onChange={event => setKey(event.target.value)} autoComplete="off" /><button type="submit" disabled={!key || busy}>Load entries</button></div></form>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {recoveryLink && <div className="operator-card" role="status"><strong>New access link</strong><p>Send privately to the provider after the callback. Anyone with this link can edit or delete the listing. It replaces access on the old device.</p><input aria-label="Recovery link" readOnly value={recoveryLink} onFocus={event => event.currentTarget.select()} /><button type="button" onClick={() => { void navigator.clipboard.writeText(recoveryLink) }}>Copy link</button></div>}
      {metrics && <section><h2>Pilot activity · last 30 days</h2><div className="metric-grid">{[['provider_started', 'Listings started'], ['provider_published', 'Listings submitted'], ['search_with_results', 'Searches with results'], ['search_without_results', 'Searches with no results'], ['contact_tapped', 'Call taps'], ['listing_reported', 'Reports'], ['listings_published', 'Live listings']].map(([event, label]) => <div key={event}><strong>{metrics[event] || 0}</strong><span>{label}</span></div>)}</div><p>Counts are aggregate; they do not track callers or prove a job was completed.</p></section>}
      <section><h2>Find a listing for recovery</h2><p>Call the listed phone number and confirm the provider before creating a new access link.</p><form onSubmit={event => { event.preventDefault(); void lookupProvider() }}><label htmlFor="lookup-phone">Provider phone number</label><div><input id="lookup-phone" inputMode="tel" value={lookupPhone} onChange={event => setLookupPhone(event.target.value)} /><button type="submit" disabled={busy || !key || lookupPhone.replace(/\D/g, '').length < 10}>Find</button></div></form>{lookupResults.map(provider => <article className="operator-card" key={provider.id}><strong>{provider.name}</strong><p>{provider.services.join(', ')} · {provider.area} · {provider.status}</p><button type="button" disabled={busy} onClick={() => void recoverProvider(provider.id)}>Create access link after callback</button></article>)}</section>
      <section><h2>Pending entries</h2>{providers.length === 0 ? <p>{metrics ? 'No pending entries.' : 'Load entries to review submissions.'}</p> : providers.map(provider => <article className="operator-card" key={provider.id}><h3>{provider.name}</h3><p>{provider.services.join(', ')} · {provider.area} · {provider.delivery}</p><p>Phone: {provider.phone} · Hours: {provider.hours || 'unspecified'}</p><div><button type="button" disabled={busy} onClick={() => void decideStatus(provider, 'published')}>Approve after callback</button><button type="button" disabled={busy} onClick={() => void decideStatus(provider, 'rejected')}>Reject</button></div></article>)}</section>
      <section><h2>Customer reports</h2>{reports.length === 0 ? <p>{metrics ? 'No open reports.' : 'Load entries to review customer reports.'}</p> : reports.map(report => <article className="operator-card" key={report.id}><strong>{report.name}</strong><p>{report.reason}</p><p>Phone: {report.phone} · Status: {report.status}</p><small>{new Date(report.created_at).toLocaleString()}</small><div><button type="button" disabled={busy} onClick={() => void resolveReport(report, 'checked')}>Checked, keep listing</button><button type="button" disabled={busy} onClick={() => void resolveReport(report, 'hidden')}>Hide listing</button><button type="button" disabled={busy} onClick={() => void recoverProvider(report.provider_id)}>Recover after callback</button></div></article>)}</section>
    </main></div>
}
