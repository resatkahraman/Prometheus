import { useEffect, useState } from 'react';
import { useLocale } from '../../i18n/LocaleContext';
import { getDesktopModelCatalog } from '../../lib/desktopBridge';
import type { DesktopModelCatalog } from '../../types/desktop';

export function AgentModelWorkbench() {
  const { t } = useLocale();
  const [catalog, setCatalog] = useState<DesktopModelCatalog | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => { let disposed = false; void getDesktopModelCatalog().then(value => { if (!disposed) setCatalog(value); }).catch(() => { if (!disposed) setUnavailable(true); }); return () => { disposed = true; }; }, []);
  if (unavailable) return <section className="empty"><div className="eyebrow">{t.nav.agents.toUpperCase()}</div><h1>{t.nav.agents}</h1><p>{t.coreOffline}</p></section>;
  if (!catalog) return <section className="empty"><div className="eyebrow">{t.nav.agents.toUpperCase()}</div><h1>{t.nav.agents}</h1><p>{t.status}</p></section>;
  const availability = (value: string) => ({ available: t.available, not_installed: t.notInstalled, unavailable: t.unavailable, error: t.error }[value] ?? value);
  return <section className="home"><div className="eyebrow">{t.nav.agents.toUpperCase()}</div><h1>{t.nav.agents}</h1><div className="missionEvents"><b>{t.agentInventory}</b>{catalog.agents.slice(0, 128).map((agent, index) => <pre className="reviewCode" key={index}>{JSON.stringify(agent, null, 2)}</pre>)}</div><div className="missionEvents"><b>{t.modelInventory}</b>{catalog.models.map(model => <div key={model.route_key}><span>{model.display_name}</span><small>{model.canonical_id}</small><small>{t.provider}: {model.provider} · {t.availability}: {availability(model.availability)} · {model.cost_class}</small><small>{t.capabilities}: {model.capabilities.join(', ')}</small>{model.configured_context_tokens && <small>{t.configuredContext}: {model.configured_context_tokens} {t.tokens}</small>}<small>{t.noObservations}</small></div>)}</div><div className="missionEvents"><b>{t.routing}</b><span>{catalog.routing_information}</span></div></section>;
}
