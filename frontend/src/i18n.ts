import english from './locales/en-IN.json'
import bengali from './locales/bn-IN.json'
import gujarati from './locales/gu-IN.json'
import hindi from './locales/hi-IN.json'
import kannada from './locales/kn-IN.json'
import malayalam from './locales/ml-IN.json'
import marathi from './locales/mr-IN.json'
import punjabi from './locales/pa-IN.json'
import tamil from './locales/ta-IN.json'
import telugu from './locales/te-IN.json'

export const languages = [
  { code: 'bn-IN', native: 'বাংলা', english: 'Bengali' },
  { code: 'en-IN', native: 'English', english: 'English' },
  { code: 'gu-IN', native: 'ગુજરાતી', english: 'Gujarati' },
  { code: 'hi-IN', native: 'हिन्दी', english: 'Hindi' },
  { code: 'kn-IN', native: 'ಕನ್ನಡ', english: 'Kannada' },
  { code: 'ml-IN', native: 'മലയാളം', english: 'Malayalam' },
  { code: 'mr-IN', native: 'मराठी', english: 'Marathi' },
  { code: 'pa-IN', native: 'ਪੰਜਾਬੀ', english: 'Punjabi' },
  { code: 'ta-IN', native: 'தமிழ்', english: 'Tamil' },
  { code: 'te-IN', native: 'తెలుగు', english: 'Telugu' },
] as const

export type LanguageCode = typeof languages[number]['code']
export type CopyKey = keyof typeof english

const copy: Record<LanguageCode, Record<CopyKey, string>> = {
  'bn-IN': bengali, 'en-IN': english, 'gu-IN': gujarati, 'hi-IN': hindi, 'kn-IN': kannada,
  'ml-IN': malayalam, 'mr-IN': marathi, 'pa-IN': punjabi, 'ta-IN': tamil, 'te-IN': telugu,
}

export function isLanguageCode(value: string): value is LanguageCode {
  return languages.some(item => item.code === value)
}

export function ui(language: string, key: CopyKey, values: Record<string, string | number> = {}): string {
  const template = (isLanguageCode(language) ? copy[language] : english)[key] || english[key]
  return template.replace(/\{(\w+)\}/g, (match, name: string) => values[name] === undefined ? match : String(values[name]))
}
