import { createContext, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { detectInitialLocale, persistLocale, type Locale } from './locale';
import { translations, type TranslationDictionary } from './translations';

type LocaleContextValue = { locale: Locale; setLocale: (locale: Locale) => void; t: TranslationDictionary };
const Context = createContext<LocaleContextValue>({ locale: 'en', setLocale: () => {}, t: translations.en });
export function LocaleProvider({ children }: { children: ReactNode }) { const [locale, set] = useState<Locale>(detectInitialLocale); const setLocale = (next: Locale) => { set(next); persistLocale(next); }; const value = useMemo(() => ({ locale, setLocale, t: translations[locale] }), [locale]); return <Context.Provider value={value}>{children}</Context.Provider>; }
export const useLocale = () => useContext(Context);
