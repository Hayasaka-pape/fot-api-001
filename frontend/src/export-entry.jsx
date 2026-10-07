import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api } from './shared.jsx';
import { OverlayFrame, useOverlayViewport } from './overlay-runtime.jsx';
import { startPolling } from './polling.js';
import './styles.css';

function Snapshot() {
  const [config] = useState(() => JSON.parse(document.getElementById('config').textContent));
  const [data, setData] = useState(() => JSON.parse(document.getElementById('data').textContent));
  const [stale, setStale] = useState(false), size = useOverlayViewport();
  useEffect(() => {
    if (!config.connectedApiUrl) return;
    // ZIP owns its embedded layout; fetching server scene edits would silently alter the exported artifact.
    return startPolling({ load: signal => api(config.connectedApiUrl, { signal, cache: 'no-store' }), onResult: value => { setData(value); setStale(false); }, onError: () => setStale(true), intervalSeconds: config.pollInterval, immediate: false });
  }, [config]);
  return <OverlayFrame scene={config} data={data} size={size} stale={stale} snapshot={config.snapshot} />;
}
createRoot(document.getElementById('root')).render(<Snapshot />);
