import { summary } from '../src/view-model.js';
if (summary(3) !== '90 TL') throw new Error('contract');
