import type { Locale } from './locale';

const englishTranslations = {
  nav: { home: 'Home', command: 'Command', projects: 'Projects', missions: 'Missions', approvals: 'Approvals', changes: 'Changes', agents: 'Agents', activity: 'Activity', memory: 'Memory', settings: 'Settings' },
  brand: 'PROMETHEUS', center: 'Command Center', eyebrow: 'COMMAND CENTER',
  heading: 'Direct Prometheus with precision.', support: 'Direct Prometheus, inspect work, and review authority before execution.',
  quick: 'Quick Access', recent: 'Recent', start: 'Start Mission', open: 'Open Project', review: 'Review Approvals',
  ask: 'Ask Prometheus or start a command...', search: 'Search or command...', core: 'Prometheus Core',
  notConfigured: 'Not configured', preview: 'Preview mode', bridgeError: 'Native bridge error', filesystem: 'Filesystem', shell: 'Shell', process: 'Process', remote: 'Remote network', denied: 'Denied', authority: 'Canonical authority', safety: 'Safety', enforced: 'Enforced', surface: 'Surface', mode: 'Mode', desktop: 'Desktop', webview: 'Webview', restricted: 'Restricted', context: 'CONTEXT', security: 'SECURITY', navigate: 'NAVIGATE', actions: 'ACTIONS', settingsTitle: 'Language / Dil', switchTr: 'Switch to Turkish', switchEn: 'Switch to English', empty: 'Prometheus Core transport is not configured in DESKTOP-001.', projectsEmpty: 'Projects will appear here after the secure core bridge is connected.', desktopLabel: 'Prometheus Desktop',
} as const;

const turkishTranslations = {
  nav: { home: 'Ana Sayfa', command: 'Komut', projects: 'Projeler', missions: 'Görevler', approvals: 'Onaylar', changes: 'Değişiklikler', agents: 'Ajanlar', activity: 'Etkinlik', memory: 'Hafıza', settings: 'Ayarlar' },
  brand: 'PROMETHEUS', center: 'Komuta Merkezi', eyebrow: 'KOMUTA MERKEZİ',
  heading: "Prometheus'u hassasiyetle yönetin.", support: "Prometheus'u yönlendirin, çalışmaları inceleyin ve yürütmeden önce yetkiyi gözden geçirin.",
  quick: 'Hızlı Erişim', recent: 'Son Kullanılanlar', start: 'Görev Başlat', open: 'Proje Aç', review: 'Onayları İncele',
  ask: "Prometheus'a sorun veya bir komut başlatın...", search: 'Ara veya komut gir...', core: 'Prometheus Core',
  notConfigured: 'Yapılandırılmadı', preview: 'Önizleme modu', bridgeError: 'Yerel köprü hatası', filesystem: 'Dosya sistemi', shell: 'Kabuk', process: 'İşlem', remote: 'Uzak ağ', denied: 'İzin yok', authority: 'Kanonik yetki', safety: 'Güvenlik', enforced: 'Etkin', surface: 'Yüzey', mode: 'Mod', desktop: 'Masaüstü', webview: 'Web görünümü', restricted: 'Kısıtlı', context: 'BAĞLAM', security: 'GÜVENLİK', navigate: 'GEZİN', actions: 'EYLEMLER', settingsTitle: 'DİL / LANGUAGE', switchTr: 'Türkçe', switchEn: 'İngilizceye geç', empty: 'Prometheus Core bağlantısı DESKTOP-001 içinde henüz yapılandırılmadı.', projectsEmpty: 'Güvenli çekirdek bağlantısı kurulduğunda projeler burada görünecek.', desktopLabel: 'Prometheus Masaüstü',
} as const;

type Widen<T> = { [K in keyof T]: T[K] extends string ? string : T[K] extends object ? Widen<T[K]> : T[K] };
export type TranslationDictionary = Widen<typeof englishTranslations>;
export const translations: Record<Locale, TranslationDictionary> = { en: englishTranslations, tr: turkishTranslations };
