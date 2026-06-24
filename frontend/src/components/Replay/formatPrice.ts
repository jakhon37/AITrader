/** Decimal places for FX price display and input rounding. */
export function priceDecimals(instrument: string): number {
  return instrument.toUpperCase().includes('JPY') ? 3 : 5;
}

export function roundPrice(price: number, instrument = 'EURUSD'): number {
  if (!Number.isFinite(price)) return 0;
  const decimals = priceDecimals(instrument);
  return Number(price.toFixed(decimals));
}

export function formatPrice(price: number, instrument = 'EURUSD'): string {
  return roundPrice(price, instrument).toFixed(priceDecimals(instrument));
}

export function priceInputStep(instrument = 'EURUSD'): string {
  return priceDecimals(instrument) === 3 ? '0.001' : '0.00001';
}