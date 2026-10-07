import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Canvas } from './shared.jsx';
import './styles.css';

function Snapshot() {
  const config = JSON.parse(document.getElementById('config').textContent);
  const [data, setData] = useState(() => JSON.parse(document.getElementById('data').textContent));
  const [stale, setStale] = useState(false), [size, setSize] = useState({ width: innerWidth, height: innerHeight });
  useEffect(() => {
    document.body.classList.add('overlay-body');
    document.documentElement.classList.add('overlay-html');
    const resize = () => setSize({ width: innerWidth, height: innerHeight });
    window.addEventListener('resize', resize);
    let active = true, busy = false;
    const controller = new AbortController();
    const refresh = async () => {
      if (!active || busy || !config.connectedApiUrl) return;
      busy = true;
      try { const response = await fetch(config.connectedApiUrl, { signal: controller.signal, cache: 'no-store' }); if (!response.ok) throw new Error('取得失敗'); const value = await response.json(); if (active) { setData(value); setStale(false); } }
      catch (failure) { if (active && failure.name !== 'AbortError') setStale(true); }
      finally { busy = false; }
    };
    const timer = config.connectedApiUrl ? setInterval(refresh, Math.max(30, config.pollInterval || 30) * 1000) : null;
    return () => { active = false; clearInterval(timer); controller.abort(); window.removeEventListener('resize', resize); };
  }, []);
  const scale = Math.min(size.width / config.canvas.width, size.height / config.canvas.height);
  return <div className="overlay-root"><div style={{ transform: `scale(${scale})`, transformOrigin: 'top left' }}><Canvas scene={config} data={data} /></div>{stale && <div className="overlay-stale">更新に失敗 · 最終取得データを表示中</div>}{config.snapshot && data.source !== 'demo' && <div className="snapshot-badge">SNAPSHOT · 固定データ</div>}</div>;
}
createRoot(document.getElementById('root')).render(<Snapshot />);
