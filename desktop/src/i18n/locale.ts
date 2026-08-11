export type Locale='tr'|'en';
const KEY='prometheus.ui.language';
export function detectInitialLocale():Locale{try{const saved=localStorage.getItem(KEY);if(saved==='tr'||saved==='en')return saved}catch{};try{return navigator.language.toLowerCase().startsWith('tr')?'tr':'en'}catch{return'en'}}
export function persistLocale(locale:Locale){try{localStorage.setItem(KEY,locale)}catch{} }
