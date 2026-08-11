import { useEffect, useState } from 'react';
import { ActivityRail } from './components/navigation/ActivityRail';
import { ContextSidebar } from './components/navigation/ContextSidebar';
import { TitleBar } from './components/window/TitleBar';
import { StatusBar } from './components/status/StatusBar';
import { HomeWorkbench, type DesktopCommandResult } from './components/workbench/HomeWorkbench';
import { InspectorPanel } from './components/workbench/InspectorPanel';
import { CommandCenter } from './components/command/CommandCenter';
import { getDesktopBootstrap, getDesktopCoreStatus, submitDesktopCommand } from './lib/desktopBridge';
import type { CoreStatus, DesktopCommandResponse, NavigationView } from './types/desktop';
import { useLocale } from './i18n/LocaleContext';

export default function App() {
  const [view, setView] = useState<NavigationView>('home');
  const [open, setOpen] = useState(false);
  const [coreStatus, setCoreStatus] = useState<CoreStatus>({ state: 'connecting', code: 'connecting', message: 'Connecting...' });
  const [submitting, setSubmitting] = useState(false);
  const [commandResult, setCommandResult] = useState<DesktopCommandResult | null>(null);
  const { t, locale, setLocale } = useLocale();
  useEffect(() => { let disposed = false; let inFlight = false; let timer: number | undefined; const refresh = async () => { if (inFlight) return; inFlight = true; try { const status = await getDesktopCoreStatus(); if (!disposed) setCoreStatus(status); } finally { inFlight = false; } }; void getDesktopBootstrap().then(() => refresh()).catch(() => { if (!disposed) setCoreStatus({ state: 'core_error', code: 'core_error', message: 'Core bootstrap failed.' }); }); timer = window.setInterval(() => { void refresh(); }, 5000); return () => { disposed = true; if (timer !== undefined) window.clearInterval(timer); }; }, []);
  const handleSubmitCommand = async (message: string): Promise<DesktopCommandResponse> => { setSubmitting(true); setCommandResult({ state: 'submitting', text: t.sending }); try { const response = await submitDesktopCommand(message); setCommandResult({ state: response.requires_approval ? 'requires_approval' : response.status, text: response.summary || t.commandAccepted }); return response; } catch (error) { const code = typeof error === 'object' && error && 'code' in error ? String(error.code) : 'core_error'; setCommandResult({ state: code === 'timeout' || code === 'core_offline' ? 'uncertain' : 'error', text: code === 'timeout' || code === 'core_offline' ? t.commandUncertain : t.commandFailed }); throw error; } finally { setSubmitting(false); } };
  return <div className="app"><TitleBar onSearch={() => setOpen(true)} /><div className="body"><ActivityRail active={view} onSelect={setView} /><ContextSidebar active={view} onSelect={setView} /><main>{view === 'home' ? <HomeWorkbench coreStatus={coreStatus} submitting={submitting} commandResult={commandResult} onSubmitCommand={handleSubmitCommand} /> : view === 'settings' ? <section className="empty"><div className="eyebrow">{t.nav.settings.toUpperCase()}</div><h1>{t.nav.settings}</h1><p>{t.core} · {t.notConfigured}</p><div className="language"><div className="eyebrow">{t.settingsTitle}</div><button className={locale === 'tr' ? 'selected' : ''} onClick={() => setLocale('tr')}>{t.switchTr}</button><button className={locale === 'en' ? 'selected' : ''} onClick={() => setLocale('en')}>{t.switchEn}</button></div></section> : <section className="empty"><div className="eyebrow">{t.nav[view].toUpperCase()}</div><h1>{t.nav[view]}</h1><p>{t.empty}</p></section>}</main><InspectorPanel coreStatus={coreStatus} /></div><StatusBar state={coreStatus.state} />{open && <CommandCenter onClose={() => setOpen(false)} onSelect={setView} />}</div>;
}
