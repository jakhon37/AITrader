import { useState, useEffect, useRef, useCallback } from 'react';
import { 
  startReplay, 
  pauseReplay, 
  resumeReplay, 
  placeManualOrder,
  cancelPendingOrder,
  modifyPendingOrder,
  closeManualPosition,
  closePositionLeg,
  modifyOpenPosition,
  stopReplay,
  getReplayState,
  getSessionAnalytics,
  changeReplayTimeframe,
  changeReplaySpeed,
  changeReplayIndicators
} from '../../api/client';
import { CandleChart } from '../Chart/CandleChart';
import { ChartViewportToggle } from '../Chart/ChartViewportToggle';
import type { ChartViewportMode } from '../Chart/utils';
import {
  getOrderLevelDefaults,
  getStopFromTakeProfit,
  getTakeProfitFromStop,
  TIMEFRAME_VIEW_MIN_PCT,
  type BarRange,
} from '../Chart/orderDefaults';
import type { OrderLinesViewContext } from '../Chart/utils';
import { ReplayConfig } from './components/ReplayConfig';
import { SessionAnalyticsPanel } from './components/SessionAnalyticsPanel';
import type { SessionAnalytics } from './types/analytics';
import { ActiveSessionHeader } from './components/ActiveSessionHeader';
import { OrderTicket } from './components/OrderTicket';
import { PortfolioState } from './components/PortfolioState';
import { SessionTradeLog } from './components/SessionTradeLog';
import type { PendingOrder } from './types';
import { formatPrice, roundPrice } from './formatPrice';

interface ReplayPageProps {
  sidebarHidden: boolean;
}

export function ReplayPage({ sidebarHidden }: ReplayPageProps) {
  // Session Configuration State
  const [instrument, setInstrument] = useState('EURUSD');
  const [timeframe, setTimeframe] = useState('1h');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [initialCapital, setInitialCapital] = useState(10000);
  const [mode, setMode] = useState<'watch' | 'manual'>('manual');
  const [speed, setSpeed] = useState(10);
  const [calculateIndicators, setCalculateIndicators] = useState(true);

  // Active Session State
  const [isActive, setIsActive] = useState(false);
  const [status, setStatus] = useState<'paused' | 'running' | 'ended'>('paused');
  const [currentTime, setCurrentTime] = useState<string | null>(null);
  const [sessionState, setSessionState] = useState<any>(null);
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [analyticsData, setAnalyticsData] = useState<SessionAnalytics | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analyticsFinalMode, setAnalyticsFinalMode] = useState(false);
  const wasRunningBeforeAnalyticsRef = useRef(false);
  const sessionEndAnalyticsOpenedRef = useRef(false);

  // Manual Order Panel State
  const [orderSize, setOrderSize] = useState(1.0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Optional Entry, Stop Loss, and Take Profit levels
  const [presetEnabled, setPresetEnabled] = useState(false);
  const [presetEntryPrice, setPresetEntryPrice] = useState<number>(0);
  const [slEnabled, setSlEnabled] = useState(false);
  const [slPrice, setSlPrice] = useState<number>(0);
  const [tpEnabled, setTpEnabled] = useState(false);
  const [tpPrice, setTpPrice] = useState<number>(0);
  const [orderDraftKey, setOrderDraftKey] = useState(0);
  const [orderLinesFocusKey, setOrderLinesFocusKey] = useState(0);
  const [recentCandleRange, setRecentCandleRange] = useState<OrderLinesViewContext | null>(null);
  const [currentBarClose, setCurrentBarClose] = useState(0);
  const [chartViewportMode, setChartViewportMode] = useState<ChartViewportMode>(() => {
    const saved = localStorage.getItem('replay_chart_viewport');
    return saved === 'fit-all' ? 'fit-all' : 'auto';
  });

  const [orderSide, setOrderSide] = useState<'buy' | 'sell'>('buy');
  const [selectedPendingOrderId, setSelectedPendingOrderId] = useState<string | null>(null);
  const [selectedOpenLegId, setSelectedOpenLegId] = useState<string | null>(null);

  // Auto Scroll Refs
  const tradeLogEndRef = useRef<HTMLDivElement>(null);
  const recentBarsRef = useRef<BarRange[]>([]);

  // Resize and Toggle panel states
  const [rightHidden, setRightHidden] = useState(() => {
    return localStorage.getItem('replay_right_hidden') === 'true';
  });
  const [leftWidth, setLeftWidth] = useState(70);
  const [ticketHeight, setTicketHeight] = useState(42);
  const [portfolioHeight, setPortfolioHeight] = useState(28);
  const [ticketCollapsed, setTicketCollapsed] = useState(() => {
    return localStorage.getItem('replay_ticket_collapsed') === 'true';
  });
  const [chartLayoutKey, setChartLayoutKey] = useState(0);
  const chartPanelRef = useRef<HTMLDivElement>(null);
  const layoutRowRef = useRef<HTMLDivElement>(null);

  const handleToggleTicketCollapsed = (collapsed: boolean) => {
    setTicketCollapsed(collapsed);
    localStorage.setItem('replay_ticket_collapsed', String(collapsed));
  };

  const handleToggleRightPanel = () => {
    setRightHidden((prev) => {
      const next = !prev;
      localStorage.setItem('replay_right_hidden', String(next));
      return next;
    });
  };

  const handleLeftRightDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = leftWidth;
    const container = e.currentTarget.parentElement;
    if (!container) return;
    const containerWidth = container.getBoundingClientRect().width;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaPercent = (deltaX / containerWidth) * 100;
      setLeftWidth(Math.max(20, Math.min(85, startWidth + deltaPercent)));
    };

    const onMouseUp = () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      setChartLayoutKey((k) => k + 1);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  const handleVerticalDrag1 = (e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startTicketHeight = ticketHeight;
    const container = e.currentTarget.parentElement;
    if (!container) return;
    const containerHeight = container.getBoundingClientRect().height;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const deltaY = moveEvent.clientY - startY;
      const deltaPercent = (deltaY / containerHeight) * 100;
      const nextTicketHeight = Math.max(10, Math.min(65, startTicketHeight + deltaPercent));
      if (nextTicketHeight + portfolioHeight <= 90) {
        setTicketHeight(nextTicketHeight);
      }
    };

    const onMouseUp = () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  const handleVerticalDrag2 = (e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startPortfolioHeight = portfolioHeight;
    const container = e.currentTarget.parentElement;
    if (!container) return;
    const containerHeight = container.getBoundingClientRect().height;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const deltaY = moveEvent.clientY - startY;
      const deltaPercent = (deltaY / containerHeight) * 100;
      const nextPortfolioHeight = Math.max(10, Math.min(50, startPortfolioHeight + deltaPercent));
      if (ticketHeight + nextPortfolioHeight <= 90) {
        setPortfolioHeight(nextPortfolioHeight);
      }
    };

    const onMouseUp = () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  // Restore active replay session once backend is reachable
  useEffect(() => {
    let cancelled = false;

    const restore = async () => {
      try {
        const res = await getReplayState();
        if (cancelled || res.status !== 'active') return;
        setIsActive(true);
        setMode(res.session.mode);
        setStatus(res.session.status);
        setInstrument(res.session.instrument);
        if (res.session.timeframe) {
          setTimeframe(res.session.timeframe);
        }
        setSpeed(res.session.speed);
        setCurrentTime(res.session.current_time);
        setSessionState(res.session);
        if (res.session.calculate_indicators !== undefined) {
          setCalculateIndicators(res.session.calculate_indicators);
        }
      } catch {
        // Backend banner handles offline state; avoid noisy console errors on startup
      }
    };

    restore();
    return () => {
      cancelled = true;
    };
  }, []);



  // Auto-scroll trade log
  useEffect(() => {
    tradeLogEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [sessionState?.trade_history]);

  const pendingOrders: PendingOrder[] = sessionState?.pending_orders ?? [];

  // Reset presets on instrument or active session change
  useEffect(() => {
    setPresetEnabled(false);
    setPresetEntryPrice(0);
    setSlEnabled(false);
    setSlPrice(0);
    setTpEnabled(false);
    setTpPrice(0);
    recentBarsRef.current = [];
    setRecentCandleRange(null);
  }, [instrument, isActive]);

  // Re-space SL/TP when timeframe changes so levels stay visible on the new scale
  useEffect(() => {
    const entry = presetEnabled ? presetEntryPrice : currentClosePrice;
    if (entry <= 0 || (!slEnabled && !tpEnabled)) return;
    const { sl, tp } = getDefaults(orderSide, entry);
    if (slEnabled) setSlPrice(sl);
    if (tpEnabled) setTpPrice(tp);
    updateRecentCandleRange(recentBarsRef.current, entry);
    bumpOrderLinesFocus();
  }, [timeframe]);

  const handleStart = async () => {
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const payload = {
        instrument,
        start_date: `${startDate}T00:00:00Z`,
        initial_capital: initialCapital,
        mode,
        speed: mode === 'watch' ? speed : 0.0,
        timeframe,
        calculate_indicators: calculateIndicators,
      };
      const res = await startReplay(payload);
      if (res.status === 'success') {
        setIsActive(true);
        setSessionState(res.session);
        setStatus(res.session.status);
        setCurrentTime(res.session.current_time);
        if (res.session.timeframe) {
          setTimeframe(res.session.timeframe);
        }
        setShowAnalytics(false);
        setAnalyticsData(null);
        setAnalyticsFinalMode(false);
        sessionEndAnalyticsOpenedRef.current = false;
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to start replay session.');
    }
  };

  const handlePause = async () => {
    try {
      const res = await pauseReplay();
      if (res.status === 'success') {
        setStatus('paused');
      }
    } catch (err) {
      console.error('Pause failed:', err);
    }
  };

  const handleResume = async () => {
    try {
      const res = await resumeReplay();
      if (res.status === 'success') {
        setStatus('running');
      }
    } catch (err) {
      console.error('Resume failed:', err);
    }
  };

  const openEndedSessionAnalytics = useCallback(async () => {
    setAnalyticsLoading(true);
    try {
      const res = await getSessionAnalytics();
      if (res.analytics) {
        setAnalyticsData(res.analytics);
        setShowAnalytics(true);
        setAnalyticsFinalMode(true);
        setIsActive(false);
        setStatus('ended');
      }
    } catch {
      try {
        const res = await stopReplay();
        if (res.status === 'success' && res.report) {
          setAnalyticsData(res.report);
          setShowAnalytics(true);
          setAnalyticsFinalMode(true);
          setIsActive(false);
          setStatus('ended');
        }
      } catch (err) {
        console.error('Failed to load session analytics:', err);
      }
    } finally {
      setAnalyticsLoading(false);
    }
  }, []);

  // Listen for real-time WebSocket frames via custom event
  useEffect(() => {
    const handleReplayFrame = (e: Event) => {
      const customEvent = e as CustomEvent<any>;
      const { session_state, bar } = customEvent.detail;
      if (bar?.close) {
        setCurrentBarClose(bar.close);
      }
      if (session_state) {
        setSessionState(session_state);
        setStatus(session_state.status);
        setCurrentTime(session_state.current_time);
        if (session_state.timeframe) {
          setTimeframe(session_state.timeframe);
        }
        if (session_state.calculate_indicators !== undefined) {
          setCalculateIndicators(session_state.calculate_indicators);
        }

        if (session_state.status === 'ended' && !sessionEndAnalyticsOpenedRef.current) {
          sessionEndAnalyticsOpenedRef.current = true;
          void openEndedSessionAnalytics();
        }
      }
    };
    window.addEventListener('replay_frame', handleReplayFrame);
    return () => window.removeEventListener('replay_frame', handleReplayFrame);
  }, [openEndedSessionAnalytics]);

  const handleOpenAnalytics = async () => {
    if (mode !== 'manual') return;
    setAnalyticsLoading(true);
    setErrorMsg(null);
    wasRunningBeforeAnalyticsRef.current = status === 'running';
    if (status === 'running') {
      await handlePause();
    }
    try {
      const res = await getSessionAnalytics();
      if (res.status === 'success' && res.analytics) {
        setAnalyticsData(res.analytics);
        setAnalyticsFinalMode(false);
        setShowAnalytics(true);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load session analytics.');
    } finally {
      setAnalyticsLoading(false);
    }
  };

  const handleContinueFromAnalytics = async () => {
    setShowAnalytics(false);
    if (wasRunningBeforeAnalyticsRef.current) {
      await handleResume();
    }
    wasRunningBeforeAnalyticsRef.current = false;
  };

  const handleEndSessionFromAnalytics = async () => {
    setAnalyticsLoading(true);
    try {
      const res = await stopReplay();
      if (res.status === 'success') {
        setIsActive(false);
        setStatus('ended');
        if (res.report) {
          setAnalyticsData(res.report);
        }
        setAnalyticsFinalMode(true);
        setShowAnalytics(true);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to end session.');
    } finally {
      setAnalyticsLoading(false);
    }
  };

  const handleCloseFinalAnalytics = () => {
    setShowAnalytics(false);
    setAnalyticsData(null);
    setAnalyticsFinalMode(false);
  };

  const handleTimeframeChange = async (newTf: string) => {
    try {
      const res = await changeReplayTimeframe(newTf);
      if (res.status === 'success') {
        setTimeframe(newTf);
        if (res.session) {
          setSessionState(res.session);
          setCurrentTime(res.session.current_time);
        }
      }
    } catch (err) {
      console.error('Failed to change timeframe:', err);
    }
  };

  const currentClosePrice = currentBarClose || 0;

  // Fill limit entry with live replay price once bars start arriving
  useEffect(() => {
    if (presetEnabled && presetEntryPrice <= 0 && currentClosePrice > 0) {
      setPresetEntryPrice(currentClosePrice);
    }
  }, [presetEnabled, presetEntryPrice, currentClosePrice]);

  const handleChartViewportChange = (mode: ChartViewportMode) => {
    setChartViewportMode(mode);
    localStorage.setItem('replay_chart_viewport', mode);
  };

  const getDefaults = (side: 'buy' | 'sell', entry: number) =>
    getOrderLevelDefaults(timeframe, side, entry, recentBarsRef.current, instrument);

  const bumpOrderLinesFocus = () => setOrderLinesFocusKey((k) => k + 1);

  const updateRecentCandleRange = (bars: BarRange[], entry: number) => {
    if (bars.length < 3) {
      setRecentCandleRange({ entry, minSpanPct: TIMEFRAME_VIEW_MIN_PCT[timeframe] ?? 0.012 });
      return;
    }
    const slice = bars.slice(-40);
    setRecentCandleRange({
      candleLow: Math.min(...slice.map((b) => b.low)),
      candleHigh: Math.max(...slice.map((b) => b.high)),
      entry,
      minSpanPct: TIMEFRAME_VIEW_MIN_PCT[timeframe] ?? 0.012,
    });
  };

  const handleTogglePreset = (enabled: boolean) => {
    setPresetEnabled(enabled);
    if (enabled && currentClosePrice > 0) {
      setPresetEntryPrice(roundPrice(currentClosePrice, instrument));
    }
  };

  const handleToggleSL = (enabled: boolean) => {
    setSlEnabled(enabled);
    if (enabled) {
      const entry = presetEnabled ? presetEntryPrice : currentClosePrice;
      if (tpEnabled && tpPrice > 0 && entry > 0) {
        setSlPrice(getStopFromTakeProfit(orderSide, entry, tpPrice, instrument));
      } else {
        const { sl } = getDefaults(orderSide, entry);
        setSlPrice(sl);
      }
      bumpOrderLinesFocus();
    }
  };

  const handleToggleTP = (enabled: boolean) => {
    setTpEnabled(enabled);
    if (enabled) {
      const entry = presetEnabled ? presetEntryPrice : currentClosePrice;
      if (slEnabled && slPrice > 0 && entry > 0) {
        setTpPrice(getTakeProfitFromStop(orderSide, entry, slPrice, instrument));
      } else {
        const { tp } = getDefaults(orderSide, entry);
        setTpPrice(tp);
      }
      bumpOrderLinesFocus();
    }
  };

  const handleToggleSide = (side: 'buy' | 'sell') => {
    setOrderSide(side);
    const entry = presetEnabled ? presetEntryPrice : currentClosePrice;
    const { sl, tp } = getDefaults(side, entry);
    if (slEnabled) setSlPrice(sl);
    if (tpEnabled) setTpPrice(tp);
  };

  const handlePositionSelect = useCallback((pos: { entry: number; sl: number; tp: number } | null) => {
    if (pos) {
      setSelectedPendingOrderId(null);
      setSelectedOpenLegId(null);
      setPresetEnabled(true);
      setPresetEntryPrice(pos.entry);
      setSlEnabled(true);
      setSlPrice(pos.sl);
      setTpEnabled(true);
      setTpPrice(pos.tp);
      updateRecentCandleRange(recentBarsRef.current, pos.entry);
    }
  }, [timeframe]);

  const clearOrderDraft = useCallback(() => {
    setPresetEnabled(false);
    setPresetEntryPrice(0);
    setSlEnabled(false);
    setSlPrice(0);
    setTpEnabled(false);
    setTpPrice(0);
    setOrderDraftKey((k) => k + 1);
  }, []);

  /** Reset chart draft but keep limit-entry mode on for placing another preset order. */
  // Clear open-position edit when leg closes
  useEffect(() => {
    if (!selectedOpenLegId) return;
    const stillOpen = sessionState?.open_positions?.some((p: { leg_id?: string }) => p.leg_id === selectedOpenLegId);
    if (!stillOpen) {
      setSelectedOpenLegId(null);
    }
  }, [sessionState?.open_positions, selectedOpenLegId]);

  const prepareNextLimitOrder = useCallback(() => {
    setSelectedPendingOrderId(null);
    setSelectedOpenLegId(null);
    setPresetEnabled(true);
    setPresetEntryPrice(currentClosePrice > 0 ? currentClosePrice : 0);
    setSlEnabled(false);
    setSlPrice(0);
    setTpEnabled(false);
    setTpPrice(0);
    setOrderDraftKey((k) => k + 1);
    if (currentClosePrice > 0) {
      updateRecentCandleRange(recentBarsRef.current, currentClosePrice);
      bumpOrderLinesFocus();
    }
  }, [currentClosePrice, timeframe]);

  // Clear chart edit state when selected pending order fills or is cancelled
  useEffect(() => {
    if (!selectedPendingOrderId) return;
    const stillPending = pendingOrders.some((o) => o.order_id === selectedPendingOrderId);
    if (!stillPending) {
      prepareNextLimitOrder();
    }
  }, [pendingOrders, selectedPendingOrderId, prepareNextLimitOrder]);

  const handleClearOpenPositionSelection = useCallback(() => {
    setSelectedOpenLegId(null);
    clearOrderDraft();
  }, [clearOrderDraft]);

  const loadOpenPositionToChart = useCallback((pos: { leg_id?: string; side: string; entry_price: number; sl?: number | null; tp?: number | null }) => {
    if (!pos.leg_id) return;
    if (pos.leg_id === selectedOpenLegId) {
      handleClearOpenPositionSelection();
      return;
    }
    setSelectedOpenLegId(pos.leg_id);
    setSelectedPendingOrderId(null);
    const side = pos.side.toLowerCase() === 'buy' || pos.side.toLowerCase() === 'long' ? 'buy' : 'sell';
    const hasSl = pos.sl != null && pos.sl > 0;
    const hasTp = pos.tp != null && pos.tp > 0;
    const { sl, tp } = getDefaults(side, pos.entry_price);
    setPresetEnabled(true);
    setPresetEntryPrice(roundPrice(pos.entry_price, instrument));
    setOrderSide(side);
    setSlEnabled(true);
    setSlPrice(hasSl ? roundPrice(pos.sl!, instrument) : sl);
    setTpEnabled(true);
    setTpPrice(hasTp ? roundPrice(pos.tp!, instrument) : tp);
    updateRecentCandleRange(recentBarsRef.current, pos.entry_price);
    bumpOrderLinesFocus();
  }, [selectedOpenLegId, handleClearOpenPositionSelection, instrument, timeframe]);

  const openPositionDraft = selectedOpenLegId
    ? { slPrice, tpPrice, slEnabled, tpEnabled }
    : undefined;

  const handleOpenPositionSlToggle = useCallback((enabled: boolean) => {
    setSlEnabled(enabled);
  }, []);

  const handleOpenPositionTpToggle = useCallback((enabled: boolean) => {
    setTpEnabled(enabled);
  }, []);

  const handleOpenPositionSlChange = useCallback((price: number) => {
    setSlPrice(roundPrice(price, instrument));
  }, [instrument]);

  const handleOpenPositionTpChange = useCallback((price: number) => {
    setTpPrice(roundPrice(price, instrument));
  }, [instrument]);

  const loadPendingOrderToChart = useCallback((order: PendingOrder) => {
    setSelectedOpenLegId(null);
    setSelectedPendingOrderId(order.order_id);
    setOrderSide(order.side);
    setOrderSize(order.size_lots);
    setPresetEnabled(true);
    setPresetEntryPrice(order.entry_price);
    setSlEnabled(order.sl != null && order.sl > 0);
    setSlPrice(order.sl ?? 0);
    setTpEnabled(order.tp != null && order.tp > 0);
    setTpPrice(order.tp ?? 0);
    updateRecentCandleRange(recentBarsRef.current, order.entry_price);
    bumpOrderLinesFocus();
  }, [timeframe]);

  const handleClearPendingSelection = useCallback(() => {
    prepareNextLimitOrder();
  }, [prepareNextLimitOrder]);

  const handleSelectPendingOrder = useCallback((order: PendingOrder) => {
    loadPendingOrderToChart(order);
  }, [loadPendingOrderToChart]);

  const handleCancelPendingOrder = async () => {
    if (!selectedPendingOrderId) return;
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await cancelPendingOrder(selectedPendingOrderId);
      if (res.status === 'success') {
        setSessionState(res.session);
        prepareNextLimitOrder();
        setSuccessMsg('Pending limit order cancelled.');
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to cancel pending order.');
    }
  };

  const handleUpdatePendingOrder = async () => {
    if (!selectedPendingOrderId) return;
    setErrorMsg(null);
    setSuccessMsg(null);
    if (presetEntryPrice <= 0) {
      setErrorMsg('Set a limit entry price before updating.');
      return;
    }
    try {
      const entry = presetEntryPrice;
      const sl = slEnabled ? slPrice : null;
      const tp = tpEnabled ? tpPrice : null;
      const res = await modifyPendingOrder(
        selectedPendingOrderId,
        orderSide,
        orderSize,
        entry,
        sl,
        tp,
      );
      if (res.status === 'success') {
        setSessionState(res.session);
        setSuccessMsg(`Limit ${orderSide.toUpperCase()} updated @ ${formatPrice(entry, instrument)}`);
        const updated = res.session.pending_orders?.find(
          (o: PendingOrder) => o.order_id === selectedPendingOrderId,
        );
        if (updated) {
          loadPendingOrderToChart(updated);
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to update pending order.');
    }
  };

  const handleBuy = async () => {
    setErrorMsg(null);
    setSuccessMsg(null);
    if (presetEnabled && presetEntryPrice <= 0) {
      setErrorMsg('Set a limit entry price before placing.');
      return;
    }
    try {
      const entry = presetEnabled ? presetEntryPrice : null;
      const sl = slEnabled ? slPrice : null;
      const tp = tpEnabled ? tpPrice : null;
      const res = await placeManualOrder('buy', orderSize, entry, sl, tp);
      if (res.status === 'success') {
        setSessionState(res.session);
        if (res.order.status === 'pending') {
          setSuccessMsg(`Limit BUY ${orderSize} lots queued @ ${formatPrice(res.order.limit_price ?? 0, instrument)}`);
          setTicketCollapsed(false);
          prepareNextLimitOrder();
        } else {
          setSuccessMsg(`Market BUY ${orderSize} lots filled at ${res.order.filled_price}`);
          clearOrderDraft();
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to execute Buy order.');
    }
  };

  const handleSell = async () => {
    setErrorMsg(null);
    setSuccessMsg(null);
    if (presetEnabled && presetEntryPrice <= 0) {
      setErrorMsg('Set a limit entry price before placing.');
      return;
    }
    try {
      const entry = presetEnabled ? presetEntryPrice : null;
      const sl = slEnabled ? slPrice : null;
      const tp = tpEnabled ? tpPrice : null;
      const res = await placeManualOrder('sell', orderSize, entry, sl, tp);
      if (res.status === 'success') {
        setSessionState(res.session);
        if (res.order.status === 'pending') {
          setSuccessMsg(`Limit SELL ${orderSize} lots queued @ ${formatPrice(res.order.limit_price ?? 0, instrument)}`);
          setTicketCollapsed(false);
          prepareNextLimitOrder();
        } else {
          setSuccessMsg(`Market SELL ${orderSize} lots filled at ${res.order.filled_price}`);
          clearOrderDraft();
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to execute Sell order.');
    }
  };

  const handleCloseLeg = async (legId: string) => {
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await closePositionLeg(legId);
      if (res.status === 'success') {
        setSessionState(res.session);
        if (legId === selectedOpenLegId) {
          setSelectedOpenLegId(null);
          clearOrderDraft();
        }
        setSuccessMsg(`Closed position leg at ${res.order.filled_price}`);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to close position.');
    }
  };

  const handleModifyLeg = async (
    legId: string,
    stopLoss: number | null,
    takeProfit: number | null,
    options?: { clearSl?: boolean; clearTp?: boolean },
  ) => {
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await modifyOpenPosition(
        legId,
        stopLoss != null ? roundPrice(stopLoss, instrument) : null,
        takeProfit != null ? roundPrice(takeProfit, instrument) : null,
        options,
      );
      if (res.status === 'success') {
        setSessionState(res.session);
        setSuccessMsg('Position SL/TP updated.');
        const updated = res.session.open_positions?.find((p: { leg_id?: string; sl?: number | null; tp?: number | null; entry_price?: number }) => p.leg_id === legId);
        if (updated) {
          const hasSl = updated.sl != null && updated.sl > 0;
          const hasTp = updated.tp != null && updated.tp > 0;
          setPresetEnabled(true);
          setPresetEntryPrice(roundPrice(updated.entry_price ?? presetEntryPrice, instrument));
          setSlEnabled(hasSl);
          setSlPrice(hasSl ? roundPrice(updated.sl!, instrument) : 0);
          setTpEnabled(hasTp);
          setTpPrice(hasTp ? roundPrice(updated.tp!, instrument) : 0);
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to update position levels.');
    }
  };

  const handleSpeedChange = async (newSpeed: number) => {
    setSpeed(newSpeed);
    try {
      await changeReplaySpeed(newSpeed);
    } catch (err) {
      console.error('Failed to change speed:', err);
    }
  };

  const handleIndicatorsChange = async (checked: boolean) => {
    setCalculateIndicators(checked);
    try {
      await changeReplayIndicators(checked);
    } catch (err) {
      console.error('Failed to change indicators status:', err);
    }
  };

  const formatDateTime = (isoString: string | null) => {
    if (!isoString) return '--';
    const dt = new Date(isoString);
    return dt.toUTCString().replace('GMT', 'UTC');
  };

  const formatCurrency = (val: number | undefined) => {
    if (val === undefined) return '$0.00';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
  };

  // 1. Setup Configuration View
  if (!isActive && !showAnalytics) {
    return (
      <ReplayConfig
        instrument={instrument}
        setInstrument={setInstrument}
        timeframe={timeframe}
        setTimeframe={setTimeframe}
        startDate={startDate}
        setStartDate={setStartDate}
        initialCapital={initialCapital}
        setInitialCapital={setInitialCapital}
        mode={mode}
        setMode={setMode}
        speed={speed}
        setSpeed={setSpeed}
        calculateIndicators={calculateIndicators}
        setCalculateIndicators={setCalculateIndicators}
        handleStart={handleStart}
        errorMsg={errorMsg}
      />
    );
  }

  // 2. Final analytics only (session ended)
  if (!isActive && showAnalytics && analyticsData) {
    return (
      <SessionAnalyticsPanel
        analytics={analyticsData}
        instrument={instrument}
        formatCurrency={formatCurrency}
        loading={analyticsLoading}
        finalMode
        onClose={handleCloseFinalAnalytics}
      />
    );
  }

  // 3. Active Session View (+ optional analytics overlay)
  return (
    <div style={{ display: 'grid', gridTemplateRows: '56px 1fr', height: '100vh', overflow: 'hidden' }}>
      <ActiveSessionHeader
        instrument={instrument}
        timeframe={timeframe}
        mode={mode}
        currentTime={currentTime}
        formatDateTime={formatDateTime}
        status={status}
        handlePause={handlePause}
        handleResume={handleResume}
        speed={speed}
        onSpeedChange={handleSpeedChange}
        calculateIndicators={calculateIndicators}
        onIndicatorsChange={handleIndicatorsChange}
        onShowAnalytics={handleOpenAnalytics}
        sidebarHidden={sidebarHidden}
        rightPanelHidden={rightHidden}
        onToggleRightPanel={handleToggleRightPanel}
      />

      <div
        ref={layoutRowRef}
        style={{
        display: 'flex',
        padding: 12,
        overflow: 'hidden',
        height: 'calc(100vh - 56px)',
        boxSizing: 'border-box',
        width: '100%',
        gap: 0,
      }}>
        {/* Left: Chart */}
        <div
          ref={chartPanelRef}
          className="glass-panel"
          style={{
            flex: rightHidden ? '1 1 auto' : `0 0 ${leftWidth}%`,
            minWidth: 0,
            display: 'flex',
            flexDirection: 'column',
            padding: 12,
            overflow: 'hidden',
            boxSizing: 'border-box',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <span style={{ fontWeight: 700, fontSize: 14, color: '#fff' }}>{instrument}</span>
              <div style={{ display: 'flex', background: '#111827', borderRadius: 6, padding: 2, border: '1px solid var(--border-glow)' }}>
                {['1m', '5m', '15m', '30m', '1h', '4h', '1d'].map((tf) => (
                  <button
                    key={tf}
                    onClick={() => handleTimeframeChange(tf)}
                    style={{
                      background: timeframe === tf ? 'var(--neon-cyan-glow)' : 'transparent',
                      border: 'none',
                      color: timeframe === tf ? '#fff' : 'var(--text-secondary)',
                      padding: '4px 10px',
                      borderRadius: 4,
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                    }}
                  >
                    {tf}
                  </button>
                ))}
              </div>
              <ChartViewportToggle mode={chartViewportMode} onChange={handleChartViewportChange} />
            </div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Historical Simulation</span>
          </div>
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <CandleChart
              instrument={instrument}
              timeframe={timeframe}
              virtualEndTime={currentTime || undefined}
              viewportMode={chartViewportMode}
              entryLinePrice={presetEnabled ? presetEntryPrice : null}
              slLinePrice={slEnabled ? slPrice : null}
              tpLinePrice={tpEnabled ? tpPrice : null}
              onPositionSelect={handlePositionSelect}
              onUpdateEntryPrice={(price) => setPresetEntryPrice(roundPrice(price, instrument))}
              onUpdateSLPrice={handleOpenPositionSlChange}
              onUpdateTPPrice={handleOpenPositionTpChange}
              orderDraftKey={orderDraftKey}
              orderLinesFocusKey={orderLinesFocusKey}
              recentCandleRange={recentCandleRange ?? undefined}
              layoutKey={chartLayoutKey}
              panelRef={chartPanelRef}
              layoutRowRef={layoutRowRef}
              panelVisible={!rightHidden}
              ticketCollapsed={ticketCollapsed}
              onNewBar={(bar) => {
                if (bar.close > 0) setCurrentBarClose(bar.close);
                recentBarsRef.current = [
                  ...recentBarsRef.current.slice(-39),
                  { high: bar.high, low: bar.low },
                ];
              }}
            />
          </div>
        </div>

        {/* Divider left-right — stay mounted so chart column width transitions reliably */}
        <div
          className="resize-handle-h"
          onMouseDown={rightHidden ? undefined : handleLeftRightDrag}
          style={{
            width: rightHidden ? 0 : 6,
            minWidth: rightHidden ? 0 : 6,
            overflow: 'hidden',
            opacity: rightHidden ? 0 : 1,
            pointerEvents: rightHidden ? 'none' : 'auto',
            flexShrink: 0,
          }}
        />

        {/* Right: Operations, Position, and Trade Log */}
        <div
          aria-hidden={rightHidden}
          style={{
            flex: rightHidden ? '0 0 0px' : '1 1 0',
            minWidth: 0,
            width: rightHidden ? 0 : undefined,
            overflow: 'hidden',
            visibility: rightHidden ? 'hidden' : 'visible',
            pointerEvents: rightHidden ? 'none' : 'auto',
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            gap: 0,
          }}
        >
            {/* Row 1: Order Ticket */}
            <div
              style={{
                height: ticketCollapsed ? 'auto' : `${ticketHeight}%`,
                minHeight: ticketCollapsed ? undefined : 220,
                flexShrink: 0,
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <OrderTicket
                orderSize={orderSize}
                setOrderSize={setOrderSize}
                handleBuy={handleBuy}
                handleSell={handleSell}
                errorMsg={errorMsg}
                successMsg={successMsg}
                isCollapsed={ticketCollapsed}
                onToggleCollapse={() => handleToggleTicketCollapsed(!ticketCollapsed)}
                mode={mode}
                presetEnabled={presetEnabled}
                presetEntryPrice={presetEntryPrice}
                setPresetEntryPrice={setPresetEntryPrice}
                onTogglePreset={handleTogglePreset}
                slEnabled={slEnabled}
                slPrice={slPrice}
                setSlPrice={setSlPrice}
                onToggleSL={handleToggleSL}
                tpEnabled={tpEnabled}
                tpPrice={tpPrice}
                setTpPrice={setTpPrice}
                onToggleTP={handleToggleTP}
                orderSide={orderSide}
                onToggleSide={handleToggleSide}
                currentClosePrice={currentClosePrice}
                pendingOrders={pendingOrders}
                selectedPendingOrderId={selectedPendingOrderId}
                onSelectPendingOrder={handleSelectPendingOrder}
                onClearPendingSelection={handleClearPendingSelection}
                onCancelPendingOrder={handleCancelPendingOrder}
                onUpdatePendingOrder={handleUpdatePendingOrder}
                editingOpenPosition={!!selectedOpenLegId}
                onClearOpenPositionSelection={handleClearOpenPositionSelection}
                instrument={instrument}
              />
            </div>

            {/* Divider 1 */}
            {!ticketCollapsed && (
              <div className="resize-handle-v" onMouseDown={handleVerticalDrag1} />
            )}

            {/* Row 2: Portfolio State */}
            <div style={{ height: `${portfolioHeight}%`, minHeight: 120, flexShrink: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              <PortfolioState
                sessionState={sessionState}
                formatCurrency={formatCurrency}
                instrument={instrument}
                mode={mode}
                selectedOpenLegId={selectedOpenLegId}
                openPositionDraft={openPositionDraft}
                successMsg={selectedOpenLegId ? successMsg : null}
                onSelectOpenPosition={loadOpenPositionToChart}
                onDraftSlToggle={handleOpenPositionSlToggle}
                onDraftTpToggle={handleOpenPositionTpToggle}
                onDraftSlChange={handleOpenPositionSlChange}
                onDraftTpChange={handleOpenPositionTpChange}
                onCloseLeg={handleCloseLeg}
                onModifyLeg={handleModifyLeg}
              />
            </div>

            {/* Divider 2 */}
            <div className="resize-handle-v" onMouseDown={handleVerticalDrag2} />

            {/* Row 3: Session Trade Log */}
            <div style={{ flex: 1, minHeight: 100, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              <SessionTradeLog
                sessionState={sessionState}
                tradeLogEndRef={tradeLogEndRef}
              />
            </div>
        </div>
      </div>

      {showAnalytics && analyticsData && !analyticsFinalMode && (
        <SessionAnalyticsPanel
          analytics={analyticsData}
          instrument={instrument}
          formatCurrency={formatCurrency}
          loading={analyticsLoading}
          onContinue={handleContinueFromAnalytics}
          onEndSession={handleEndSessionFromAnalytics}
          onClose={handleContinueFromAnalytics}
        />
      )}
    </div>
  );
}
