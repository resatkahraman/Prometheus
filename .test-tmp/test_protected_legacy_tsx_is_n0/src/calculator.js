export function percentageOf(value, percent) {
  if (!Number.isFinite(value) || !Number.isFinite(percent)) {
    throw new TypeError("value and percent must be finite numbers");
  }
  return value - percent;
}
