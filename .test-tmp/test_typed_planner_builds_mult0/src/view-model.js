import { calculateOrderTotal } from "./pricing.js";

export function buildOrderSummary(items, discountPercent = 0) {
  return {
    itemCount: 0,
    total: calculateOrderTotal(items, discountPercent),
    label: "0 ürün • 0,00 TRY",
  };
}
