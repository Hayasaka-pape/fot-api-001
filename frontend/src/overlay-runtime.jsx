import React, { useEffect, useState } from 'react';
import { Canvas } from './shared.jsx';

export function useOverlayViewport() {
  const [size, setSize] = useState({ width: innerWidth, height: innerHeight });
  useEffect(() => {
    const hadBodyClass = document.body.classList.contains('overlay-body'), hadHtmlClass = document.documentElement.classList.contains('overlay-html');
    // Body-only transparency leaves the document background visible in OBS; both layers must be transparent.
    document.body.classList.add('overlay-body'); document.documentElement.classList.add('overlay-html');
    const resize = () => setSize({ width: innerWidth, height: innerHeight });
    window.addEventListener('resize', resize);
    return () => { window.removeEventListener('resize', resize); if (!hadBodyClass) document.body.classList.remove('overlay-body'); if (!hadHtmlClass) document.documentElement.classList.remove('overlay-html'); };
  }, []);
  return size;
}

export function OverlayFrame({ scene, data, size, stale = false, snapshot = false }) {
  const scale = Math.min(size.width / scene.canvas.width, size.height / scene.canvas.height);
  return <div className="overlay-root"><div style={{ transform: `scale(${scale})`, transformOrigin: 'top left' }}><Canvas scene={scene} data={data} /></div>{stale && <div className="overlay-stale">更新に失敗 · 最終取得データを表示中</div>}{snapshot && data.source !== 'demo' && <div className="snapshot-badge">SNAPSHOT · 固定データ</div>}</div>;
}
