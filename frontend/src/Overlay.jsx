import React, { useEffect, useRef, useState } from 'react';
import { api, Canvas } from './shared.jsx';

export default function Overlay({ id }) {
  const [scene, setScene] = useState(null), [data, setData] = useState(null), [error, setError] = useState(''), [size, setSize] = useState({ width: innerWidth, height: innerHeight });
  const current = useRef(null);
  useEffect(() => {
    document.body.classList.add('overlay-body');
    document.documentElement.classList.add('overlay-html');
    const resize = () => setSize({ width: innerWidth, height: innerHeight });
    window.addEventListener('resize', resize);
    let active = true, timer;
    const controller = new AbortController();
    async function poll() {
      try {
        const nextScene = await api(`/api/scenes/${encodeURIComponent(id)}`, { signal: controller.signal });
        const nextData = await api(`/api/scenes/${encodeURIComponent(id)}/data`, { signal: controller.signal });
        if (active) { current.current = nextScene; setScene(nextScene); setData(nextData); setError(''); }
      } catch (failure) { if (active && failure.name !== 'AbortError') setError(failure.message); }
      if (active) timer = setTimeout(poll, Math.max(30, current.current?.pollInterval || 30) * 1000);
    }
    poll();
    return () => { active = false; clearTimeout(timer); controller.abort(); window.removeEventListener('resize', resize); document.body.classList.remove('overlay-body'); document.documentElement.classList.remove('overlay-html'); };
  }, [id]);
  if (!scene) return <div className="overlay-initial">{error ? `オーバーレイを取得できません：${error}` : 'オーバーレイを読み込み中…'}</div>;
  const scale = Math.min(size.width / scene.canvas.width, size.height / scene.canvas.height);
  return <div className="overlay-root"><div style={{ transform: `scale(${scale})`, transformOrigin: 'top left' }}><Canvas scene={scene} data={data} /></div>{error && <div className="overlay-stale">更新に失敗 · 最終取得データを表示中</div>}</div>;
}
