import type { ReactNode } from 'react';

export type IconName = 'home' | 'command' | 'projects' | 'missions' | 'approvals' | 'changes' | 'agents' | 'activity' | 'memory' | 'settings';

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const common = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  const paths: Record<IconName, ReactNode> = {
    home: <><path d="m3 10 9-7 9 7" /><path d="M5 9v11h14V9" /><path d="M9 20v-6h6v6" /></>,
    command: <><circle cx="7" cy="7" r="2.5" /><circle cx="17" cy="17" r="2.5" /><path d="m9 9 6 6" /><path d="m15 9-6 6" /></>,
    projects: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 9h18M8 5l1-2h6l1 2" /></>,
    missions: <><path d="m12 3 2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2L12 3Z" /></>,
    approvals: <><path d="m5 12 4 4L19 6" /></>,
    changes: <><path d="M4 7h16M4 12h10M4 17h16" /><path d="m17 10 3 2-3 2" /></>,
    agents: <><circle cx="12" cy="8" r="3" /><path d="M5 21a7 7 0 0 1 14 0M4 11H2M22 11h-2M12 2V1" /></>,
    activity: <><path d="M3 12h4l2-7 4 14 2-7h6" /></>,
    memory: <><rect x="4" y="5" width="16" height="14" rx="2" /><path d="M8 9h8M8 13h5M8 17h3" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.8 1.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5v.1h-2.6v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1-1.8-1.8.1-.1A1.7 1.7 0 0 0 8 15a1.7 1.7 0 0 0-1.5-1H6v-2h.5A1.7 1.7 0 0 0 8 11a1.7 1.7 0 0 0-.3-1.9l-.1-.1 1.8-1.8.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.5V6H15v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1 1.8 1.8-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1h.1v2h-.1a1.7 1.7 0 0 0-1.5 1Z" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" {...common}>{paths[name]}</svg>;
}
