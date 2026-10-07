import React from 'react';
import { Shield, Users, Trophy, MapPin, CalendarDays } from 'lucide-react';

export const SECTION_NAMES = { scoreboard: 'スコアボード', stats: '試合スタッツ', lineup: '出場選手', fixtures: '試合日程', standings: '順位表', team: 'チーム情報', league: 'リーグ情報', squad: '選手一覧' };
export const KINDS = { match: { label: '試合', sections: ['scoreboard', 'stats', 'lineup', 'fixtures'], icon: 'match' }, date: { label: '日付別', sections: ['fixtures'], icon: 'date' }, team: { label: 'チーム', sections: ['team', 'fixtures', 'squad', 'stats', 'standings'], icon: 'team' }, league: { label: 'リーグ', sections: ['league', 'standings', 'fixtures', 'stats'], icon: 'league' } };
export const INITIAL_QUERY = { kind: 'match', id: '5315746', date: new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' }), timezone: 'Asia/Tokyo', timeout: 15, mode: 'demo' };
export const DEFAULT_WIDGETS = {
  scoreboard: { x: 110, y: 84, width: 1700, height: 230, fontSize: 32 },
  stats: { x: 110, y: 360, width: 630, height: 430, fontSize: 28 },
  lineup: { x: 790, y: 360, width: 1020, height: 430, fontSize: 26 },
  fixtures: { x: 110, y: 800, width: 1700, height: 270, fontSize: 28 },
  standings: { x: 750, y: 100, width: 1060, height: 780, fontSize: 26 },
  team: { x: 110, y: 100, width: 590, height: 280, fontSize: 32 },
  league: { x: 110, y: 100, width: 590, height: 240, fontSize: 32 },
  squad: { x: 110, y: 430, width: 590, height: 570, fontSize: 25 },
};
export const makeWidget = section => ({ id: section, section, ...DEFAULT_WIDGETS[section] });
export const makeScene = () => ({ name: 'MATCHDAY / メイン', query: { ...INITIAL_QUERY }, sections: ['scoreboard', 'stats', 'lineup', 'fixtures'], canvas: { width: 1920, height: 1080, background: 'transparent' }, theme: { accent: '#b8ef55', background: '#15191d', text: '#f5f7f8', opacity: 0.94 }, widgets: ['scoreboard', 'stats', 'lineup', 'fixtures'].map(makeWidget), pollInterval: 30 });

export async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } });
  if (!response.ok) {
    let detail;
    try { const result = await response.json(); detail = result.error?.message || result.message || result.detail?.message || (typeof result.detail === 'string' ? result.detail : null); } catch { /* server may return text */ }
    throw new Error(detail || `取得できませんでした（HTTP ${response.status}）`);
  }
  return response.status === 204 ? null : response.json();
}
export function timeLabel(value, timezone = 'Asia/Tokyo') {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('ja-JP', { timeZone: timezone, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
}
export function filteredData(data, sections) {
  if (!data) return null;
  return { source: data.source, kind: data.kind, fetchedAt: data.fetchedAt, modules: Object.fromEntries(sections.filter(section => data.modules?.[section] != null).map(section => [section, data.modules[section]])), warnings: data.warnings || [], unavailable: data.unavailable || [] };
}
export function initials(name) { return String(name || '?').split(/\s+/).filter(Boolean).map(s => s[0]).slice(0, 3).join('').toUpperCase(); }

function EmptyModule({ section }) { return <div className="module-empty"><Shield size="1.4em" /><span>{SECTION_NAMES[section]}</span><small>このデータは提供されていません</small></div>; }
function ModuleHeading({ children, eyebrow, detail }) { return <header className="module-heading"><span>{eyebrow}</span><h3>{children}</h3>{detail && <small>{detail}</small>}</header>; }
function TeamCrest({ team, away = false }) { return <div className={`team-crest ${away ? 'away' : ''}`}><Shield /><b>{initials(team?.shortName || team?.name)}</b></div>; }
function Scoreboard({ data, timezone }) {
  return <div className="scoreboard-module"><div className="scoreboard-meta"><span>{data.league || 'MATCHDAY'}</span><span className="match-status"><i />{data.status || '予定'} {data.clock ? ` · ${data.clock}` : ''}</span></div><div className="scoreboard-main"><div className="score-team home"><TeamCrest team={data.home} /><div><small>HOME</small><h3>{data.home?.name || 'Home'}</h3></div></div><div className="score-numbers"><b>{data.home?.score ?? '–'}</b><span>:</span><b>{data.away?.score ?? '–'}</b></div><div className="score-team away"><div><small>AWAY</small><h3>{data.away?.name || 'Away'}</h3></div><TeamCrest team={data.away} away /></div></div><div className="scoreboard-foot"><span>WATCH ALONG</span><span>{data.kickoff ? timeLabel(data.kickoff, timezone) : 'FOOTBALL LIVE'}</span></div></div>;
}
function Stats({ data }) {
  return <div className="stats-module"><ModuleHeading eyebrow="DATA INSIGHTS" detail={data.length > 6 ? `先頭 6 / 全 ${data.length} 項目 · 全件は JSON に収録` : null}>スタッツ</ModuleHeading><div className="stat-list">{(Array.isArray(data) ? data : []).slice(0, 6).map((stat, i) => {
    const home = Number.parseFloat(stat.home) || 0, away = Number.parseFloat(stat.away) || 0;
    const ratio = home + away ? home / (home + away) * 100 : 50;
    if (stat.away == null) return <div className="stat-row single-stat" key={`${stat.label}-${i}`}><div><span>{stat.label}</span><b>{String(stat.home ?? '—')}</b></div></div>;
    return <div className="stat-row" key={`${stat.label}-${i}`}><div><b>{String(stat.home ?? '—')}</b><span>{stat.label}</span><b>{String(stat.away ?? '—')}</b></div><div className="stat-track"><i style={{ width: `${ratio}%` }} /><i style={{ width: `${100 - ratio}%` }} /></div></div>;
  })}</div></div>;
}
function Lineup({ data }) {
  const legacy = !data.state, state = data.state || 'starting';
  const titles = { live: '現在の出場選手', final: '試合終了時の出場選手', starting: legacy ? '先発名簿（参考）' : '試合前の先発選手', uncertain: '出場選手', unavailable: '出場選手' };
  const eyebrows = { live: 'ON THE PITCH', final: 'FULL TIME', starting: 'STARTING XI', uncertain: 'PLAYER TRACKING', unavailable: 'PLAYERS' };
  return <div className="lineup-module">
    <ModuleHeading eyebrow={eyebrows[state] || 'PLAYERS'}>{titles[state] || '出場選手'}</ModuleHeading>
    <div className="lineup-columns">{['home', 'away'].map(side => {
      const team = data[side] || {}, players = Array.isArray(team.players) ? team.players : [];
      const tracking = team.tracking || (state === 'starting' ? 'starting' : state === 'uncertain' ? 'uncertain' : 'current');
      const unavailable = state === 'unavailable', uncertain = !unavailable && tracking === 'uncertain';
      const label = uncertain ? '交代状況 未確認' : unavailable ? '選手情報 未提供' : tracking === 'starting' || state === 'starting' ? legacy ? '先発名簿（参考）' : '試合前の先発' : state === 'final' ? '試合終了時の出場選手' : state === 'live' ? '現在の出場選手' : '交代を反映した選手';
      const statusClass = uncertain ? 'uncertain' : unavailable ? 'unavailable' : state === 'final' ? 'final' : tracking;
      return <div key={side}>
        <div className="lineup-team"><b>{team.name || side}</b><span>{team.formation ? `開始時 ${team.formation}` : '—'}</span></div>
        <div className={`lineup-roster-state ${statusClass}`}><span><i />{label}</span><small>{players.length ? players.length > 11 ? `表示 11 / ${players.length} 人` : `${players.length} 人` : '—'}</small></div>
        <div className="players-list">{players.length ? players.slice(0, 11).map((player, i) => <div key={player.id || `${player.name}-${i}`}><span className="shirt">{player.shirtNumber ?? '·'}</span><span>{player.name}</span>{player.enteredAt != null && player.enteredAt !== '' && <span className="incoming-badge">IN {String(player.enteredAt)}</span>}<small>{player.position || ''}</small></div>) : <div className={`lineup-empty-note ${uncertain ? 'uncertain-note' : ''}`} role="status">{uncertain ? <Shield size="1.2em" /> : <Users size="1.2em" />}<span>{uncertain ? '交代状況を確認できません' : '選手情報はまだありません'}{uncertain && <small>選手一覧の表示を保留しています</small>}</span></div>}</div>
      </div>;
    })}</div>
  </div>;
}
function Fixtures({ data, timezone }) {
  const list = Array.isArray(data) ? data : [];
  return <div className="fixtures-module"><ModuleHeading eyebrow="FIXTURES" detail={list.length > 16 ? `先頭 16 / 全 ${list.length} 試合 · 全件は JSON に収録` : `全 ${list.length} 試合 · 枠内に表示`}>試合日程</ModuleHeading><div className="fixture-list">{list.slice(0, 16).map((match, i) => <div className="fixture-row" key={match.id || i}><div className="fixture-time"><b>{match.status || '予定'}</b><span>{timeLabel(match.kickoff, timezone)}</span></div><span className="fixture-team">{typeof match.home === 'object' ? match.home.name : match.home}</span><b className="fixture-score">{match.homeScore ?? '–'} <span>:</span> {match.awayScore ?? '–'}</b><span className="fixture-team">{typeof match.away === 'object' ? match.away.name : match.away}</span><small>{match.league || ''}</small></div>)}</div></div>;
}
function Standings({ data }) {
  return <div className="standings-module"><ModuleHeading eyebrow="LEAGUE TABLE" detail={data.length > 24 ? `先頭 24 / 全 ${data.length} チーム · 全件は JSON に収録` : null}>順位表</ModuleHeading><table><thead><tr><th>#</th><th>クラブ</th><th>試合</th><th>勝</th><th>分</th><th>負</th><th>得失</th><th>勝点</th></tr></thead><tbody>{(Array.isArray(data) ? data : []).slice(0, 24).map((team, i) => <tr key={`${team.team}-${i}`}><td>{team.position}</td><td>{typeof team.team === 'object' ? team.team.name : team.team}</td><td>{team.played}</td><td>{team.won}</td><td>{team.drawn}</td><td>{team.lost}</td><td>{team.goalDifference}</td><td>{team.points}</td></tr>)}</tbody></table></div>;
}
function Info({ data, section }) {
  return <div className="info-module"><ModuleHeading eyebrow={section === 'team' ? 'CLUB PROFILE' : 'COMPETITION'}>{SECTION_NAMES[section]}</ModuleHeading><div className="info-name">{section === 'team' ? <Shield /> : <Trophy />}<h3>{data.name}</h3></div><div className="info-properties"><span><MapPin />{data.country || '—'}</span>{data.coach && <span><Users />{data.coach}</span>}{data.venue && <span><MapPin />{data.venue}</span>}{data.season && <span><CalendarDays />{data.season}</span>}</div></div>;
}
function Squad({ data }) {
  return <div className="squad-module"><ModuleHeading eyebrow="SQUAD" detail={data.length > 30 ? `先頭 30 / 全 ${data.length} 選手 · 全件は JSON に収録` : null}>選手一覧</ModuleHeading><div className="players-list">{(Array.isArray(data) ? data : []).slice(0, 30).map((player, i) => <div key={`${player.name}-${i}`}><span className="shirt">{player.shirtNumber ?? '·'}</span><span>{player.name}</span><small>{player.position || ''}</small></div>)}</div></div>;
}
export function Module({ section, data, timezone }) {
  if (data == null || (Array.isArray(data) && !data.length)) return <EmptyModule section={section} />;
  switch (section) {
    case 'scoreboard': return <Scoreboard data={data} timezone={timezone} />;
    case 'stats': return <Stats data={data} />;
    case 'lineup': return <Lineup data={data} />;
    case 'fixtures': return <Fixtures data={data} timezone={timezone} />;
    case 'standings': return <Standings data={data} />;
    case 'team': case 'league': return <Info data={data} section={section} />;
    case 'squad': return <Squad data={data} />;
    default: return <EmptyModule section={section} />;
  }
}
export function Canvas({ scene, data, selected, onSelect, onDrag, editing = false, canvasRef }) {
  const theme = scene.theme || {};
  return <div ref={canvasRef} className={`scene-canvas ${editing ? 'editing' : ''}`} style={{ width: scene.canvas.width, height: scene.canvas.height, background: scene.canvas.background === 'transparent' ? 'transparent' : scene.canvas.background, '--accent': theme.accent, '--panel-bg': theme.background, '--panel-opacity': theme.opacity, '--panel-text': theme.text }}>
    {scene.sections.map(section => scene.widgets.find(w => w.section === section)).filter(Boolean).map(widget => <div key={widget.id} className={`scene-widget ${selected === widget.id && editing ? 'selected' : ''}`} style={{ left: widget.x, top: widget.y, width: widget.width, height: widget.height, fontSize: widget.fontSize }} onPointerDown={editing ? e => onDrag(e, widget) : undefined} onClick={editing ? () => onSelect(widget.id) : undefined} tabIndex={editing ? 0 : undefined} role={editing ? 'button' : undefined} aria-label={editing ? `${SECTION_NAMES[widget.section]}を配置` : undefined} onKeyDown={editing ? e => { if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) { e.preventDefault(); onDrag(e, widget, { x: e.key === 'ArrowRight' ? 10 : e.key === 'ArrowLeft' ? -10 : 0, y: e.key === 'ArrowDown' ? 10 : e.key === 'ArrowUp' ? -10 : 0 }); } } : undefined}>
      {editing && selected === widget.id && <span className="widget-selection-label">{SECTION_NAMES[widget.section]} · {widget.x}, {widget.y}</span>}
      <div className="widget-inner"><Module section={widget.section} data={data?.modules?.[widget.section]} timezone={scene.query?.timezone} /></div>
    </div>)}
    {data?.source === 'demo' && <div className="canvas-demo-tag">DEMO DATA · サンプルデータ</div>}
  </div>;
}
