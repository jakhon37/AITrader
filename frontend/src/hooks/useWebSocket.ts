import { useEffect, useRef, useState } from 'react';
import { useSignalsStore } from '../store/signals';
import { usePortfolioStore } from '../store/portfolio';
import type { TradeSignal, FundamentalSignal, TechnicalSignal, PortfolioState, WsMessage } from '../types';

const WS_URL = 'ws://localhost:8000/ws';
const RECONNECT_INITIAL_MS = 1000;
const RECONNECT_MAX_MS = 30000;

function parseBusField(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object' && 'value' in value) {
    return String((value as { value: string }).value);
  }
  return String(value ?? '');
}

export function useWebSocket() {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelay = useRef(RECONNECT_INITIAL_MS);
  const isMounted = useRef(true);
  const connectGenRef = useRef(0);

  const { addTradeSignal, addFundamentalSignal, setTechnicalSignal, setHealthDiv, setWsConnected } = useSignalsStore();
  const { setPortfolio } = usePortfolioStore();

  useEffect(() => {
    isMounted.current = true;

    function connect() {
      if (!isMounted.current) return;
      const gen = ++connectGenRef.current;
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMounted.current || gen !== connectGenRef.current) {
          ws.close();
          return;
        }
        setConnected(true);
        setWsConnected(true);
        reconnectDelay.current = RECONNECT_INITIAL_MS;
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const msg: WsMessage = JSON.parse(event.data as string);
          const data = msg.data as Record<string, unknown>;
          switch (msg.type) {
            case 'trade_signal':
              addTradeSignal(data as unknown as TradeSignal);
              break;
            case 'fundamental_signal':
              addFundamentalSignal(data as unknown as FundamentalSignal);
              break;
            case 'technical_signal':
              setTechnicalSignal(data as unknown as TechnicalSignal);
              break;
            case 'portfolio_update':
              setPortfolio(data as unknown as PortfolioState);
              break;
            case 'system_health':
              setHealthDiv(data as unknown as { status: string; division: string });
              break;
            case 'ohlcv_bar': {
              const barData = data as any;
              const dt = new Date(barData.timestamp);
              const unixSeconds = Math.floor(dt.getTime() / 1000);
              const bar = {
                time: unixSeconds,
                open: barData.open,
                high: barData.high,
                low: barData.low,
                close: barData.close,
                volume: barData.volume,
              };
              const instrument = parseBusField(barData.instrument);
              const timeframe = parseBusField(barData.timeframe);
              window.dispatchEvent(
                new CustomEvent('ohlcv_bar', {
                  detail: {
                    instrument,
                    timeframe,
                    source: barData.source ?? 'unknown',
                    bar,
                  },
                })
              );
              break;
            }
            case 'replay_frame': {
              const frameData = data as any;
              window.dispatchEvent(
                new CustomEvent('replay_frame', {
                  detail: frameData,
                })
              );
              break;
            }
          }
        } catch (err) {
          console.error('WS parse error', err);
        }
      };

      ws.onclose = () => {
        if (!isMounted.current || gen !== connectGenRef.current) return;
        setConnected(false);
        setWsConnected(false);
        const delay = reconnectDelay.current;
        reconnectDelay.current = Math.min(delay * 2, RECONNECT_MAX_MS);
        setTimeout(connect, delay);
      };

      ws.onerror = () => {
        if (gen !== connectGenRef.current) return;
        ws.close();
      };
    }

    connect();
    return () => {
      isMounted.current = false;
      connectGenRef.current += 1;
      const ws = wsRef.current;
      wsRef.current = null;
      if (!ws) return;
      ws.onopen = null;
      ws.onmessage = null;
      ws.onclose = null;
      ws.onerror = null;
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      } else if (ws.readyState === WebSocket.CONNECTING) {
        ws.addEventListener('open', () => ws.close(), { once: true });
      }
    };
  }, [addTradeSignal, addFundamentalSignal, setTechnicalSignal, setHealthDiv, setPortfolio, setWsConnected]);

  return { connected, ws: wsRef };
}
