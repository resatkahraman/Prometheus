import { useEffect, useState } from 'react';
import { ActivityRail } from './components/navigation/ActivityRail';
import { ContextSidebar } from './components/navigation/ContextSidebar';
import { TitleBar } from './components/window/TitleBar';
import { StatusBar } from './components/status/StatusBar';
import { HomeWorkbench } from './components/workbench/HomeWorkbench';
import { InspectorPanel } from './components/workbench/InspectorPanel';
import { CommandCenter } from './components/command/CommandCenter';
import { bootstrap } from './lib/desktopBridge';
import type { NavigationView } from './types/desktop';
import { useLocale } from './i18n/LocaleContext';

export default function App() {
  const [view, setView] = useState<NavigationView>('home');
  const [open, setOpen] = useState(false);
  const [state, setState] = useState('preview');
  const { t, locale, setLocale } = useLocale();
  useEffect(() => { bootstrap().then((x) => setState(x.state)); const h = (e: KeyboardEvent) => { if (e.ctrlKey && e.key.toLowerCase() === 'k') { e.preventDefault(); setOpen(true); } if (e.key === 'Escape') setOpen(false); }; window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, []);
  return <div className="app"><TitleBar onSearch={() => setOpen(true)} /><div className="body"><ActivityRail active={view} onSelect={setView} /><ContextSidebar active={view} onSelect={setView} /><main>{view === 'home' ? <HomeWorkbench onCommand={() => setOpen(true)} /> : view === 'settings' ? <section className="empty"><div className="eyebrow">{t.nav.settings.toUpperCase()}</div><h1>{t.nav.settings}</h1><p>{t.core} · {t.notConfigured}</p><div className="language"><div className="eyebrow">{t.settingsTitle}</div><button className={locale === 'tr' ? 'selected' : ''} onClick={() => setLocale('tr')}>{t.switchTr}</button><button className={locale === 'en' ? 'selected' : ''} onClick={() => setLocale('en')}>{t.switchEn}</button></div></section> : <section className="empty"><div className="eyebrow">{t.nav[view].toUpperCase()}</div><h1>{t.nav[view]}</h1><p>{t.empty}</p></section>}</main><InspectorPanel /></div><StatusBar state={state} />{open && <CommandCenter onClose={() => setOpen(false)} onSelect={setView} />}</div>;
}
