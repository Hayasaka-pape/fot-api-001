import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowDownToLine, ArrowRight, Braces, CalendarDays, Check, ChevronDown, CircleHelp, Clock3, Copy, ExternalLink, Eye, Film, Grid2X2, Layers3, LayoutTemplate, LoaderCircle, Maximize2, Monitor, MousePointer2, Plus, Radio, RefreshCw, Save, Settings2, Shield, SlidersHorizontal, Sparkles, Trash2, Trophy, X } from 'lucide-react';
import { api, Canvas, filteredData, INITIAL_QUERY, KINDS, makeScene, makeWidget, SECTION_NAMES, timeLabel } from './shared.jsx';

const PRESETS = {
  match: [{ id: '5315746', name: 'Chelsea vs Manchester City' }],
  team: [{ id: '8455', name: 'Chelsea' }, { id: '8456', name: 'Manchester City' }, { id: '9825', name: 'Arsenal' }, { id: '8650', name: 'Liverpool' }],
  league: [{ id: '47', name: 'Premier League' }, { id: '87', name: 'LaLiga' }, { id: '54', name: 'Bundesliga' }, { id: '55', name: 'Serie A' }, { id: '53', name: 'Ligue 1' }, { id: '42', name: 'Champions League' }],
};
function SmallLabel({ children, extra }) { return <div className="field-label"><span>{children}</span>{extra && <small>{extra}</small>}</div>; }
function Select({ children, ...props }) { return <div className="select-wrap"><select {...props}>{children}</select><ChevronDown size={14} /></div>; }
function NumberField({ label, value, onChange, min, max, suffix }) { return <label className="number-field"><span>{label}</span><div><input type="number" value={value} min={min} max={max} onChange={e => { const number = Number(e.target.value); if (Number.isFinite(number)) onChange(Math.max(min ?? -Infinity, Math.min(max ?? Infinity, number))); }} />{suffix && <small>{suffix}</small>}</div></label>; }
function downloadJson(value) { const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'fot-overlay-data.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
function widgetsForKind(kind, sections) {
  const overrides = kind === 'date' ? { fixtures: { x: 110, y: 100, width: 1700, height: 880 } } : kind === 'team' ? { stats: { x: 110, y: 430, width: 590, height: 570 }, squad: { x: 750, y: 100, width: 490, height: 900 }, fixtures: { x: 1295, y: 100, width: 515, height: 900, fontSize: 23 } } : kind === 'league' ? { stats: { x: 110, y: 390, width: 590, height: 330, fontSize: 20 }, standings: { x: 750, y: 100, width: 1060, height: 900 }, fixtures: { x: 110, y: 760, width: 590, height: 240, fontSize: 22 } } : {};
  return sections.map(section => ({ ...makeWidget(section), ...overrides[section] }));
}
function queryKey(query) {
  return JSON.stringify({ kind: query.kind, id: query.kind === 'date' ? '' : String(query.id ?? ''), date: query.kind === 'date' ? String(query.date ?? '') : '', mode: query.mode || 'live', timezone: query.timezone || 'Asia/Tokyo', timeout: Number(query.timeout ?? 15) });
}

export default function App() {
  const [scene, setScene] = useState(makeScene), [form, setForm] = useState({ ...INITIAL_QUERY }), [data, setData] = useState(null), [scenes, setScenes] = useState([]), [selected, setSelected] = useState('scoreboard'), [tab, setTab] = useState('preview'), [loading, setLoading] = useState(true), [saving, setSaving] = useState(false), [error, setError] = useState(''), [toast, setToast] = useState(''), [advanced, setAdvanced] = useState(false), [showHelp, setShowHelp] = useState(false), [showScenes, setShowScenes] = useState(false), [deleteConfirm, setDeleteConfirm] = useState(null), [scale, setScale] = useState(0.5), [discoveredMatches, setDiscoveredMatches] = useState([]), [savedState, setSavedState] = useState('');
  const previewRef = useRef(null), canvasRef = useRef(null), seq = useRef(0), requestRef = useRef(null), sceneRef = useRef(scene), dragRef = useRef(null), toastTimer = useRef(null), busyRef = useRef(false);
  sceneRef.current = scene;
  const queryDirty = queryKey(form) !== queryKey(scene.query);
  const sceneDirty = Boolean(scene.id) && savedState !== JSON.stringify(scene);
  const matchChoices = [...PRESETS.match, ...discoveredMatches.filter(match => !PRESETS.match.some(p => p.id === match.id))];
  const targetChoices = form.kind === 'match' ? matchChoices : PRESETS[form.kind];
  const widget = scene.widgets.find(w => w.id === selected);
  const safeData = filteredData(data, scene.sections);
  const obsUrl = scene.id ? `${location.origin}/overlay/${encodeURIComponent(scene.id)}` : '';
  const sourceDemo = data ? data.source === 'demo' : scene.query.mode === 'demo';
  const notify = text => { clearTimeout(toastTimer.current); setToast(text); toastTimer.current = setTimeout(() => setToast(''), 3800); };

  async function fetchData(query, sections, silent = false, nextWidgets = null) {
    const nextSeq = ++seq.current;
    requestRef.current?.abort();
    const controller = new AbortController(); requestRef.current = controller;
    busyRef.current = true;
    if (!silent) setLoading(true);
    setError('');
    try {
      const result = await api('/api/query', { method: 'POST', body: JSON.stringify({ ...query, sections }), signal: controller.signal });
      if (nextSeq !== seq.current) return;
      setData(result); setScene(previous => ({ ...previous, query: { ...query }, sections, ...(nextWidgets ? { widgets: nextWidgets } : {}) }));
      if (Array.isArray(result.modules?.fixtures)) setDiscoveredMatches(previous => {
        const choices = result.modules.fixtures.filter(match => match.id).map(match => ({ id: String(match.id), name: `${typeof match.home === 'object' ? match.home.name : match.home} vs ${typeof match.away === 'object' ? match.away.name : match.away} · ${timeLabel(match.kickoff, query.timezone)}` }));
        return [...previous.filter(match => !choices.some(next => next.id === match.id)), ...choices];
      });
    } catch (failure) { if (nextSeq === seq.current && failure.name !== 'AbortError') setError(failure.message); }
    finally { if (nextSeq === seq.current) { busyRef.current = false; setLoading(false); } }
  }
  useEffect(() => {
    fetchData(INITIAL_QUERY, makeScene().sections);
    api('/api/scenes').then(value => setScenes(Array.isArray(value) ? value : value.scenes || [])).catch(() => {});
    return () => { requestRef.current?.abort(); clearTimeout(toastTimer.current); };
  }, []);
  useEffect(() => {
    if (!data) return;
    const timer = setInterval(() => { if (document.visibilityState === 'visible' && !dragRef.current && !busyRef.current) fetchData(sceneRef.current.query, sceneRef.current.sections, true); }, Math.max(30, scene.pollInterval) * 1000);
    return () => clearInterval(timer);
  }, [Boolean(data), scene.pollInterval]);
  useLayoutEffect(() => {
    if (tab !== 'preview' || !previewRef.current) return;
    const observer = new ResizeObserver(entries => setScale(entries[0].contentRect.width / scene.canvas.width));
    observer.observe(previewRef.current); return () => observer.disconnect();
  }, [tab, scene.canvas.width]);
  useEffect(() => {
    const move = e => {
      const drag = dragRef.current;
      if (!drag) return;
      const x = Math.round(drag.x + (e.clientX - drag.startX) / drag.scale), y = Math.round(drag.y + (e.clientY - drag.startY) / drag.scale);
      setScene(previous => ({ ...previous, widgets: previous.widgets.map(w => w.id === drag.id ? { ...w, x: Math.max(0, Math.min(previous.canvas.width - w.width, x)), y: Math.max(0, Math.min(previous.canvas.height - w.height, y)) } : w) }));
    };
    const end = () => { dragRef.current = null; };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', end); window.addEventListener('pointercancel', end);
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); window.removeEventListener('pointercancel', end); };
  }, []);

  function editQuery(key, value) {
    setForm(previous => ({ ...previous, [key]: value }));
  }
  function changeKind(kind) {
    setForm(previous => ({ ...previous, kind, id: kind === 'team' ? '8455' : kind === 'league' ? '47' : '5315746' }));
  }
  function toggleSection(section) {
    const next = scene.sections.includes(section) ? scene.sections.filter(s => s !== section) : [...scene.sections, section];
    if (!scene.widgets.some(w => w.section === section)) setScene(previous => ({ ...previous, widgets: [...previous.widgets, makeWidget(section)] }));
    setScene(previous => ({ ...previous, sections: next }));
    if (!next.includes(selected)) setSelected(next[0] || '');
    if (data && (busyRef.current || (!data.modules?.[section] && next.includes(section)))) fetchData(scene.query, next);
  }
  function runQuery() {
    const changed = form.kind !== scene.query.kind;
    const sections = changed ? KINDS[form.kind].sections.filter(s => form.kind !== 'team' || s !== 'standings') : scene.sections;
    setSelected(sections[0]);
    fetchData(form, sections, false, changed ? widgetsForKind(form.kind, sections) : null);
  }
  function openMatch(id) {
    if (!id) return;
    const query = { ...scene.query, kind: 'match', id: String(id) }, sections = KINDS.match.sections;
    setForm(query); setSelected('scoreboard'); fetchData(query, sections, false, widgetsForKind('match', sections));
  }
  function updateWidget(key, value) {
    setScene(previous => ({ ...previous, widgets: previous.widgets.map(w => {
      if (w.id !== selected) return w;
      const next = { ...w, [key]: key === 'fontSize' ? Math.round(value) : value };
      next.width = Math.min(previous.canvas.width, Math.max(80, next.width)); next.height = Math.min(previous.canvas.height, Math.max(60, next.height));
      next.x = Math.max(0, Math.min(previous.canvas.width - next.width, next.x)); next.y = Math.max(0, Math.min(previous.canvas.height - next.height, next.y));
      return next;
    }) }));
  }
  function startDrag(e, current, delta) {
    setSelected(current.id);
    if (delta) { setScene(previous => ({ ...previous, widgets: previous.widgets.map(w => w.id === current.id ? { ...w, x: Math.max(0, Math.min(previous.canvas.width - w.width, w.x + delta.x)), y: Math.max(0, Math.min(previous.canvas.height - w.height, w.y + delta.y)) } : w) })); return; }
    if (e.button !== 0) return;
    e.preventDefault();
    dragRef.current = { id: current.id, startX: e.clientX, startY: e.clientY, x: current.x, y: current.y, scale: previewRef.current.getBoundingClientRect().width / scene.canvas.width };
  }
  function applyLayout(preset) {
    const kind = scene.query.kind;
    let sections = kind === 'match' ? preset === 'score' ? ['scoreboard'] : preset === 'lower' ? ['scoreboard', 'stats'] : ['scoreboard', 'stats', 'lineup', 'fixtures'] : KINDS[kind].sections.filter(s => s !== 'stats');
    let widgets = sections.map(makeWidget);
    if (preset === 'lower' && kind === 'match') widgets = [ { ...makeWidget('scoreboard'), x: 70, y: 780, width: 1780, height: 230 }, { ...makeWidget('stats'), x: 70, y: 70, width: 590, height: 440 } ];
    if (preset === 'score' && kind === 'match') widgets = [{ ...makeWidget('scoreboard'), x: 310, y: 76, width: 1300, height: 220 }];
    if (kind !== 'match') { sections = KINDS[kind].sections.filter(s => kind !== 'team' || s !== 'standings'); widgets = widgetsForKind(kind, sections); }
    setScene(previous => ({ ...previous, sections, widgets })); setSelected(sections[0]);
    if (sections.some(section => !data?.modules?.[section])) fetchData(scene.query, sections);
    notify('レイアウトを適用しました');
  }
  async function saveScene() {
    if (queryDirty || !data || loading || !scene.name.trim()) return;
    setSaving(true);
    try {
      const saved = await api(scene.id ? `/api/scenes/${scene.id}` : '/api/scenes', { method: scene.id ? 'PUT' : 'POST', body: JSON.stringify(scene) });
      setScene(saved); setForm({ ...saved.query }); setSavedState(JSON.stringify(saved)); setScenes(previous => [...previous.filter(s => s.id !== saved.id), saved]); notify('シーンを保存しました。OBS で使用できます');
    } catch (failure) { setError(failure.message); }
    finally { setSaving(false); }
  }
  async function loadScene(id) {
    try { const saved = await api(`/api/scenes/${id}`); setData(null); setScene(saved); setForm({ ...saved.query }); setSavedState(JSON.stringify(saved)); setSelected(saved.sections[0] || ''); setShowScenes(false); await fetchData(saved.query, saved.sections); notify('シーンを読み込みました'); }
    catch (failure) { setError(failure.message); }
  }
  async function deleteScene(id) {
    try { await api(`/api/scenes/${id}`, { method: 'DELETE' }); setScenes(previous => previous.filter(s => s.id !== id)); if (scene.id === id) setScene(previous => ({ ...previous, id: undefined })); setDeleteConfirm(null); notify('シーンを削除しました'); }
    catch (failure) { setError(failure.message); }
  }
  async function copyObs() {
    try { await navigator.clipboard.writeText(obsUrl); notify('OBS ブラウザソースの URL をコピーしました'); }
    catch { notify('コピーできませんでした。下の URL を選択してコピーしてください'); }
  }
  function newScene() { const fresh = makeScene(); setData(null); setScene(fresh); setForm({ ...fresh.query }); setSelected('scoreboard'); setShowScenes(false); fetchData(fresh.query, fresh.sections); }

  return <div className="studio-app">
    <header className="topbar"><a className="brand" href="/" aria-label="FOT STUDIO"><span className="brand-mark"><Film size={19} /></span><b>FOT<span>/</span>STUDIO</b></a><div className="topbar-divider" /><span className="topbar-label">WATCH ALONG CREATOR</span><nav><button className="active" onClick={() => { setShowScenes(false); setShowHelp(false); }}>スタジオ</button><button onClick={() => setShowScenes(true)}>マイシーン<span>{scenes.length.toString().padStart(2, '0')}</span></button><button onClick={() => setShowHelp(true)}>使い方<ExternalLink size={12} /></button></nav><div className="topbar-right"><span className="ready-dot" />LOCAL WORKSPACE<Monitor size={16} /></div></header>

    <div className="page-intro"><div><div className="eyebrow"><span />YOUR MATCH. YOUR BROADCAST.</div><h1>観る熱量を、<span>配信のカタチに。</span></h1><p>試合データを選んで、あなただけの同時視聴オーバーレイを。</p></div><div className="intro-actions"><button className="button subtle" onClick={() => setShowScenes(true)}><Layers3 size={16} />シーン一覧</button><button className="button primary" onClick={saveScene} disabled={saving || queryDirty || !data || loading || !scene.name.trim()} title={queryDirty ? '変更した条件でデータを取得してから保存してください' : ''}>{saving ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />}{sceneDirty ? '変更を保存' : 'シーンを保存'}</button></div></div>

    <main className="workspace">
      <aside className="source-panel panel"><div className="panel-heading"><span><Radio size={16} />データソース</span><span className={`source-badge ${form.mode === 'live' ? 'live' : ''}`}>{form.mode === 'demo' ? 'DEMO' : 'LIVE'}</span></div><div className="source-content">
        <SmallLabel>取得モード</SmallLabel><div className="mode-switch"><button className={form.mode === 'demo' ? 'active' : ''} onClick={() => editQuery('mode', 'demo')}>デモデータ</button><button className={form.mode === 'live' ? 'active' : ''} onClick={() => editQuery('mode', 'live')}><span className="mini-dot" />実データ</button></div>
        <div className={`mode-note ${form.mode === 'live' ? 'live-note' : ''}`}>{form.mode === 'demo' ? 'レイアウト作成用のサンプルデータ' : 'FotMob から最新データを取得'}</div>
        <SmallLabel>データの種類</SmallLabel><div className="kind-tabs">{Object.entries(KINDS).map(([kind, options]) => <button key={kind} className={form.kind === kind ? 'active' : ''} onClick={() => changeKind(kind)}>{kind === 'match' ? <Shield /> : kind === 'date' ? <CalendarDays /> : kind === 'team' ? <Layers3 /> : <Trophy />}<span>{options.label}</span></button>)}</div>
        {form.kind !== 'date' && <><SmallLabel>{form.kind === 'match' ? '試合を選択' : form.kind === 'team' ? 'チームを選択' : 'リーグを選択'}</SmallLabel><Select value={targetChoices.some(p => p.id === form.id) ? form.id : 'custom'} onChange={e => { if (e.target.value !== 'custom') editQuery('id', e.target.value); else editQuery('id', ''); }}>{targetChoices.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}<option value="custom">ID を指定…</option></Select><label className="id-field"><span>FotMob ID</span><input aria-label="FotMob ID" placeholder="例：5315746" inputMode="numeric" value={form.id} onChange={e => editQuery('id', e.target.value.replace(/[^0-9]/g, ''))} /></label></>}
        {form.kind === 'date' && <><SmallLabel>試合の日付</SmallLabel><input className="date-input" type="date" aria-label="試合の日付" value={form.date} onChange={e => editQuery('date', e.target.value)} /></>}
        <button className="advanced-toggle" onClick={() => setAdvanced(!advanced)}><Settings2 size={14} />タイムゾーン・タイムアウト<ChevronDown size={14} className={advanced ? 'rotate' : ''} /></button>
        {advanced && <div className="advanced-fields"><SmallLabel>タイムゾーン</SmallLabel><Select value={form.timezone} onChange={e => editQuery('timezone', e.target.value)}><option value="Asia/Tokyo">日本（Asia/Tokyo）</option><option value="Europe/London">英国（Europe/London）</option><option value="Europe/Paris">欧州（Europe/Paris）</option><option value="America/New_York">米国（New York）</option><option value="UTC">UTC</option></Select><NumberField label="タイムアウト" value={form.timeout} min={5} max={60} suffix="秒" onChange={value => editQuery('timeout', value)} /></div>}
        <button className="button primary fetch-button" disabled={loading || (form.kind !== 'date' && !form.id) || (form.kind === 'date' && !form.date)} onClick={runQuery}>{loading ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}{loading ? 'データ取得中…' : 'データを取得'}<ArrowRight size={15} /></button>
        {queryDirty && <div className="pending-note">条件を変更しました。取得して反映</div>}
        {scene.query.kind !== 'match' && Array.isArray(data?.modules?.fixtures) && data.modules.fixtures.some(match => match.id) && <div className="fixture-picker"><SmallLabel>取得した日程から試合詳細へ</SmallLabel><Select aria-label="取得した日程から試合を選ぶ" value="" onChange={e => openMatch(e.target.value)}><option value="">試合を選んで取得…</option>{data.modules.fixtures.filter(match => match.id).map((match, i) => <option key={`${match.id}-${i}`} value={match.id}>{typeof match.home === 'object' ? match.home.name : match.home} vs {typeof match.away === 'object' ? match.away.name : match.away}</option>)}</Select></div>}
        <div className="panel-section-header"><span>表示する情報</span><small>{scene.sections.length} SELECTED</small></div>
        <div className="section-toggles">{KINDS[scene.query.kind].sections.map(section => <label key={section} className={scene.sections.includes(section) ? 'checked' : ''}><input type="checkbox" disabled={loading && !data} checked={scene.sections.includes(section)} onChange={() => toggleSection(section)} /><span className="custom-checkbox">{scene.sections.includes(section) && <Check size={12} />}</span><span>{SECTION_NAMES[section]}</span></label>)}</div>
        <div className="source-footer"><Shield size={16} /><p>映像を使わず、データで試合を楽しむ。<br /><span>サッカー同時視聴配信のために。</span></p></div>
      </div></aside>

      <section className="editor-column"><div className="editor-header"><div><div className="eyebrow">OVERLAY STUDIO</div><input className="scene-name" aria-label="シーン名" maxLength={80} value={scene.name} onChange={e => setScene(previous => ({ ...previous, name: e.target.value }))} /></div><span className="resolution-label">1920 × 1080 <span>16:9</span></span></div>
        <div className="editor-toolbar"><div className="view-tabs"><button className={tab === 'preview' ? 'active' : ''} onClick={() => setTab('preview')}><Eye size={14} />プレビュー</button><button className={tab === 'json' ? 'active' : ''} onClick={() => setTab('json')}><Braces size={14} />JSON</button></div><div className="toolbar-right"><span className={`data-indicator ${sourceDemo ? 'demo' : 'live'}`}><i />{sourceDemo ? 'DEMO DATA' : 'FOTMOB DATA'}</span><button aria-label="現在の条件で再取得" title="現在の条件で再取得" disabled={loading || !data} onClick={() => fetchData(scene.query, scene.sections)}><RefreshCw className={loading ? 'spin' : ''} size={14} /></button></div></div>
        {error && <div className="error-banner" role="alert"><span>{data ? '最終取得データを表示中。' : ''}{error}</span><button aria-label="エラーを閉じる" onClick={() => setError('')}><X size={14} /></button></div>}
        {tab === 'preview' ? <div className="preview-shell"><div className="preview-ruler"><span>0</span><span>480</span><span>960</span><span>1440</span><span>1920</span></div><div className="preview-stage" ref={previewRef} style={{ aspectRatio: `${scene.canvas.width} / ${scene.canvas.height}` }}><div className="pitch-decoration"><div className="pitch-center-circle" /><div className="pitch-center-line" /><span>FOOTBALL<br />WITHOUT THE FOOTAGE.</span></div><div className="preview-scale" style={{ transform: `scale(${scale})` }}><Canvas scene={scene} data={data} selected={selected} onSelect={setSelected} onDrag={startDrag} editing canvasRef={canvasRef} /></div>{loading && !data && <div className="preview-loading"><LoaderCircle className="spin" size={24} /><span>データを読み込んでいます</span></div>}{!scene.sections.length && <div className="preview-loading"><Layers3 size={28} /><span>左のパネルから表示する情報を選択</span></div>}</div><div className="preview-caption"><span><MousePointer2 size={13} />ドラッグで配置 · 矢印キーで 10px 移動</span><span>{Math.round(scale * 100)}%<Maximize2 size={12} /></span></div></div> : <div className="json-view"><div className="json-description"><span>選択した情報のみの JSON</span><button onClick={() => downloadJson(safeData)} disabled={!data}><ArrowDownToLine size={14} />保存</button></div><pre>{JSON.stringify(safeData || { status: 'データを取得してください' }, null, 2)}</pre></div>}
        <div className="below-preview"><div className="layout-section"><div className="panel-section-header"><span><LayoutTemplate size={15} />レイアウトプリセット</span><small>START WITH A STYLE</small></div><div className="layout-options"><button onClick={() => applyLayout('full')}><span className="layout-thumbnail full-layout"><i /><i /><i /><i /></span><span>マッチデー<small>すべての情報を一画面に</small></span></button><button onClick={() => applyLayout('lower')}><span className="layout-thumbnail lower-layout"><i /><i /></span><span>ローワーサード<small>トーク画面の下部に</small></span></button><button onClick={() => applyLayout('score')}><span className="layout-thumbnail score-layout"><i /></span><span>ミニマル<small>スコアを主役に</small></span></button></div></div>
          <div className="output-panel"><div className="output-icon"><Monitor size={23} /></div><div className="output-content"><div className="output-title">OBS に、そのまま。</div><p>{sceneDirty ? '未保存の変更があります。保存すると OBS に反映します。' : scene.id ? 'ブラウザソースに URL を貼り付けて、配信に追加。' : 'シーンを保存すると OBS 用 URL と ZIP を生成できます。'}</p>{scene.id && <input className="obs-url" aria-label="OBS ブラウザソース URL" value={obsUrl} readOnly onFocus={e => e.target.select()} />}</div><div className="output-actions"><button className="button primary" onClick={copyObs} disabled={!scene.id || sceneDirty}><Copy size={14} />URL をコピー</button>{scene.id ? <a className="export-link" href={`/api/scenes/${scene.id}/export`} download aria-disabled={sceneDirty} onClick={e => { if (sceneDirty) e.preventDefault(); }}><ArrowDownToLine size={13} />HTML / CSS / JSON を ZIP で保存</a> : <span className="export-link disabled"><ArrowDownToLine size={13} />HTML / CSS / JSON を ZIP で保存</span>}</div></div>
        </div>
        <div className="editor-status"><span><span className="ready-dot" />{data ? `最終取得 ${timeLabel(data.fetchedAt, scene.query.timezone)}` : 'データ待機中'}</span><span>{sourceDemo ? 'サンプルデータ · 実際のスコアではありません' : 'FotMob のデータ提供状況に応じて更新'}</span></div>
        {data?.warnings?.length > 0 && <div className="warnings">{data.warnings.map((warning, i) => <p key={i}>{typeof warning === 'string' ? warning : warning.message || JSON.stringify(warning)}</p>)}</div>}
      </section>

      <aside className="inspector panel"><div className="panel-heading"><span><SlidersHorizontal size={16} />レイアウト設定</span></div><div className="inspector-content"><SmallLabel>編集するパーツ</SmallLabel><Select value={selected || ''} onChange={e => setSelected(e.target.value)}>{!scene.sections.length && <option value="">パーツを選択してください</option>}{scene.sections.map(section => <option key={section} value={scene.widgets.find(w => w.section === section)?.id || section}>{SECTION_NAMES[section]}</option>)}</Select>
        {widget && scene.sections.includes(widget.section) ? <><div className="inspector-section-title">POSITION <span>px</span></div><div className="number-grid"><NumberField label="X" value={widget.x} min={0} max={scene.canvas.width - widget.width} onChange={v => updateWidget('x', v)} /><NumberField label="Y" value={widget.y} min={0} max={scene.canvas.height - widget.height} onChange={v => updateWidget('y', v)} /></div><div className="inspector-section-title">SIZE <span>px</span></div><div className="number-grid"><NumberField label="幅" value={widget.width} min={80} max={scene.canvas.width} onChange={v => updateWidget('width', v)} /><NumberField label="高さ" value={widget.height} min={60} max={scene.canvas.height} onChange={v => updateWidget('height', v)} /></div><div className="font-field"><NumberField label="文字サイズ" value={widget.fontSize} min={12} max={72} suffix="px" onChange={v => updateWidget('fontSize', v)} /></div><div className="inspector-note">枠内表示には件数の上限があります。<br />スタッツ 6・日程 16・順位 24・選手 30。<br />全件は JSON で取得できます。</div></> : <div className="inspector-note">表示する情報を選ぶと位置やサイズを調整できます。</div>}
        <div className="inspector-divider" /><div className="inspector-section-title">STYLE</div><label className="color-control"><span>アクセント</span><span><input type="color" aria-label="アクセントカラー" value={scene.theme.accent} onChange={e => setScene(previous => ({ ...previous, theme: { ...previous.theme, accent: e.target.value } }))} /><small>{scene.theme.accent.toUpperCase()}</small></span></label><label className="color-control"><span>パネル</span><span><input type="color" aria-label="パネルカラー" value={scene.theme.background} onChange={e => setScene(previous => ({ ...previous, theme: { ...previous.theme, background: e.target.value } }))} /><small>{scene.theme.background.toUpperCase()}</small></span></label><label className="color-control"><span>文字</span><span><input type="color" aria-label="文字カラー" value={scene.theme.text} onChange={e => setScene(previous => ({ ...previous, theme: { ...previous.theme, text: e.target.value } }))} /><small>{scene.theme.text.toUpperCase()}</small></span></label><label className="opacity-control"><span>パネルの不透明度<b>{Math.round(scene.theme.opacity * 100)}%</b></span><input type="range" min="0" max="1" step="0.01" aria-label="パネルの不透明度" value={scene.theme.opacity} onChange={e => setScene(previous => ({ ...previous, theme: { ...previous.theme, opacity: Number(e.target.value) } }))} /></label><SmallLabel>キャンバス背景</SmallLabel><Select value={scene.canvas.background === 'transparent' ? 'transparent' : 'solid'} onChange={e => setScene(previous => ({ ...previous, canvas: { ...previous.canvas, background: e.target.value === 'transparent' ? 'transparent' : '#101315' } }))}><option value="transparent">透過 · OBS 向け</option><option value="solid">背景色あり</option></Select>{scene.canvas.background !== 'transparent' && <input type="color" className="background-color" aria-label="キャンバス背景色" value={scene.canvas.background} onChange={e => setScene(previous => ({ ...previous, canvas: { ...previous.canvas, background: e.target.value } }))} />}
        <div className="inspector-divider" /><div className="refresh-setting"><Clock3 size={14} /><NumberField label="自動更新" value={scene.pollInterval} min={30} max={3600} suffix="秒" onChange={v => setScene(previous => ({ ...previous, pollInterval: Math.round(v) }))} /></div><p className="refresh-note">スタジオ・OBS 画面で自動更新。<br />最短 30 秒に 1 回取得します。</p><button className="help-link" onClick={() => setShowHelp(true)}><CircleHelp size={14} />OBS の設定方法<ArrowRight size={12} /></button>
      </div></aside>
    </main>
    <footer className="site-footer"><span>FOT / STUDIO</span><p>MADE FOR THE LOVE OF THE GAME.</p><span>v1.0 · LOCAL FIRST</span></footer>
    {toast && <div className="toast" role="status"><Check size={17} />{toast}</div>}
    {showHelp && <div className="modal-backdrop" onClick={() => setShowHelp(false)}><section className="modal help-modal" role="dialog" aria-modal="true" aria-labelledby="help-title" onClick={e => e.stopPropagation()}><button className="modal-close" aria-label="閉じる" onClick={() => setShowHelp(false)}><X size={20} /></button><div className="eyebrow">GO LIVE IN 3 STEPS</div><h2 id="help-title">配信に、あなたのスタイルを。</h2><div className="help-steps"><div><b>01</b><span><strong>データとパーツを選ぶ</strong><p>デモでレイアウトを作成。実データに切り替えたら「データを取得」で内容を確認します。</p></span></div><div><b>02</b><span><strong>配置して、シーンを保存</strong><p>プレビューをドラッグ、または X・Y・幅・高さを指定して調整します。最後に「シーンを保存」。</p></span></div><div><b>03</b><span><strong>OBS にブラウザソースを追加</strong><p>URL を貼り付け、幅 <em>1920</em>・高さ <em>1080</em> に設定。背景は透過にできます。起動した PC と同じ PC の OBS で localhost の URL を使用してください。</p></span></div></div><div className="help-callout"><Braces size={20} /><p>ZIP は保存時点の固定データです（自動更新なし）。<br />JSON を保存して、他のツールでも利用できます。</p></div><button className="button primary" onClick={() => setShowHelp(false)}>スタジオへ戻る<ArrowRight size={16} /></button></section></div>}
    {showScenes && <div className="modal-backdrop" onClick={() => setShowScenes(false)}><section className="modal scenes-modal" role="dialog" aria-modal="true" aria-labelledby="scenes-title" onClick={e => e.stopPropagation()}><button className="modal-close" aria-label="閉じる" onClick={() => setShowScenes(false)}><X size={20} /></button><div className="eyebrow">YOUR COLLECTION</div><h2 id="scenes-title">マイシーン</h2><p className="modal-description">試合や配信スタイルに合わせて、レイアウトを使い分ける。</p><button className="button primary" onClick={newScene}><Plus size={16} />新しいシーンを作成</button><div className="scene-list">{scenes.length ? scenes.map(saved => <div key={saved.id} className="saved-scene"><div className="saved-scene-art"><Grid2X2 size={26} /></div><div><strong>{saved.name}</strong><span>{saved.query?.mode === 'demo' ? 'DEMO' : 'LIVE'} · {saved.sections?.length || 0} パーツ · {saved.pollInterval || 30} 秒更新</span></div><button className="button subtle" onClick={() => loadScene(saved.id)}>開く<ArrowRight size={14} /></button><button className="delete-button" title="シーンを削除" aria-label={`${saved.name}を削除`} onClick={() => setDeleteConfirm(saved.id)}><Trash2 size={16} /></button>{deleteConfirm === saved.id && <div className="delete-confirm"><span>このシーンを削除しますか？ OBS の URL も無効になります。</span><button onClick={() => setDeleteConfirm(null)}>キャンセル</button><button onClick={() => deleteScene(saved.id)}>削除する</button></div>}</div>) : <div className="scene-empty"><Layers3 size={32} /><strong>最初のシーンを作りましょう</strong><p>スタジオでシーンを保存すると、ここに表示されます。</p></div>}</div></section></div>}
  </div>;
}
