import { calculatePrice } from '../src/pricing.js';
if (calculatePrice(3) !== 90) throw new Error('contract');
