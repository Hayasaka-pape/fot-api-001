import React, { useEffect, useRef, useState } from 'react';
import { api } from './shared.jsx';
import { OverlayFrame, useOverlayViewport } from './overlay-runtime.jsx';
import { startPolling } from './polling.js';

export default function Overlay({ id }) {
  const [scene, setScene] = useState(null), [data, setData] = useState(null), [error, setError] = useState('');
  const size = useOverlayViewport();
  const current = useRef(null);
  useEffect(() => {
    // Separate scene/data GETs can pair old geometry with a newly saved query; render captures one server snapshot.
    return startPolling({
      load: signal => api(`/api/scenes/${encodeURIComponent(id)}/render`, { signal }),
      onResult: result => { current.current = result.scene; setScene(result.scene); setData(result.data); setError(''); },
      onError: failure => setError(failure.message),
      intervalSeconds: () => current.current?.pollInterval,
    });
  }, [id]);
  if (!scene) return <div className="overlay-initial">{error ? `オーバーレイを取得できません：${error}` : 'オーバーレイを読み込み中…'}</div>;
  return <OverlayFrame scene={scene} data={data} size={size} stale={Boolean(error)} />;
}
