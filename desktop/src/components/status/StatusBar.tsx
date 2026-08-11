import { useLocale } from '../../i18n/LocaleContext';
export function StatusBar({ state }: { state: string }) { const { t } = useLocale(); return <footer className="statusbar"><span>{t.desktopLabel}</span><span>{t.core}: {state === 'preview' ? t.preview : state === 'native_error' ? t.bridgeError : t.notConfigured}</span><span className="spacer" /><span>{t.safety}: {t.enforced}</span></footer>; }
