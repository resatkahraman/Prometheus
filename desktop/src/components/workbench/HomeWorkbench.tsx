import type { FormEvent, KeyboardEvent } from 'react';
import { useState } from 'react';
import { useLocale } from '../../i18n/LocaleContext';
import type { CoreStatus, DesktopCommandResponse } from '../../types/desktop';

export type DesktopCommandResult = { state: string; text: string };
type HomeWorkbenchProps = { coreStatus: CoreStatus; submitting: boolean; commandResult: DesktopCommandResult | null; onSubmitCommand: (message: string) => Promise<DesktopCommandResponse> };

export function HomeWorkbench({ coreStatus, submitting, commandResult, onSubmitCommand }: HomeWorkbenchProps) {
  const { t } = useLocale();
  const [draft, setDraft] = useState('');
  const coreReady = coreStatus.state === 'ready';
  const canSubmit = draft.trim().length > 0 && coreReady && !submitting;
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const message = draft.trim(); if (!message || !coreReady || submitting) return; void onSubmitCommand(message).then(() => setDraft('')).catch(() => undefined); };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } };
  const coreLabel = coreReady ? t.coreReady : coreStatus.state === 'auth_required' ? t.coreAuthRequired : t.coreOffline;
  const readinessHint = coreStatus.state === 'auth_required' ? t.authHint : t.offlineHint;
  return <section className="home"><div className="eyebrow">{t.eyebrow}</div><h1>{t.heading}</h1><p>{t.support}</p><form className="commandSurface" onSubmit={handleSubmit}><label htmlFor="desktop-command">{t.composerLabel}</label><span className="composerHint">{t.composerHint}</span><textarea id="desktop-command" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={onKeyDown} placeholder={t.composerPlaceholder} maxLength={20000} rows={4} /><div className="composerMeta"><span className={coreReady ? 'coreReady' : 'coreOffline'}>{coreLabel}</span><button type="submit" disabled={!canSubmit}>{submitting ? t.sending : t.send}</button></div><span className="composerHint">{t.keyboardHint}</span></form>{!coreReady && <div className="composerOffline">{readinessHint}</div>}{commandResult && <div className="commandResult" role="status"><b>{t.latestResult}</b><span>{commandResult.text}</span></div>}<div className="quick"><button>{t.start}</button><button>{t.open}</button><button>{t.review}</button></div><div className="system"><div><b>{t.core.toUpperCase()}</b><span>{coreStatus.state === 'ready' ? t.ready : coreStatus.state === 'auth_required' ? t.authRequired : coreStatus.state === 'protocol_error' ? t.protocolError : coreStatus.state === 'preview' ? t.preview : t.offline}</span></div><div className="authority"><span>{t.filesystem} <b>{t.denied}</b></span><span>{t.shell} <b>{t.denied}</b></span><span>{t.process} <b>{t.denied}</b></span><span>{t.remote} <b>{t.denied}</b></span><span>{t.authority} <b>Prometheus Core</b></span></div></div></section>;
}
