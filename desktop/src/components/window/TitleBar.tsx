import { getCurrentWindow } from '@tauri-apps/api/window';
import { PrometheusMark } from '../brand/PrometheusMark';
import { useLocale } from '../../i18n/LocaleContext';
export function TitleBar({ onSearch }: { onSearch: () => void }) { const { t } = useLocale(); const w = getCurrentWindow(); return <header className="titlebar" data-tauri-drag-region><div className="brand"><PrometheusMark /><b>PROMETHEUS</b><span>{t.center}</span></div><button className="search" onClick={onSearch}>{t.search} <kbd>Ctrl K</kbd></button><div className="windowButtons"><button aria-label="Minimize" onClick={() => w.minimize()}>-</button><button aria-label="Maximize" onClick={() => w.toggleMaximize()}>□</button><button aria-label="Close" onClick={() => w.close()}>×</button></div></header>; }
