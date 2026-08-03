export function applyEncodedOperation(a, b, operator) {
  return operator === 'plus_v7' ? a + b : a - b;
}
