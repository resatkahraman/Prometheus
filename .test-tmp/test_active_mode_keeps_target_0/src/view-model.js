import { calculatePrice } from './pricing.js';
export const summary = (quantity) => `${calculatePrice(quantity)} TL`;
