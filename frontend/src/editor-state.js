export function queryKey(query, fallbackDate) {
  // Compare semantic fields: backend-added defaults/property order must not make a saved query look edited.
  return JSON.stringify({ kind: query.kind, id: query.kind === 'date' ? '' : String(query.id ?? ''), date: query.kind === 'date' ? String(query.date ?? '') : query.kind === 'match' ? String(query.date ?? fallbackDate) : '', mode: query.mode || 'live', timezone: query.timezone || 'Asia/Tokyo', timeout: Number(query.timeout ?? 15) });
}

export function sceneKey(scene, fallbackDate) {
  return JSON.stringify({
    id: scene.id || null, name: scene.name, query: queryKey(scene.query, fallbackDate), sections: scene.sections,
    canvas: { width: Number(scene.canvas.width), height: Number(scene.canvas.height), background: scene.canvas.background },
    theme: { accent: scene.theme.accent, background: scene.theme.background, text: scene.theme.text, opacity: Number(scene.theme.opacity) },
    widgets: scene.widgets.map(widget => ({ id: widget.id, section: widget.section, x: Number(widget.x), y: Number(widget.y), width: Number(widget.width), height: Number(widget.height), fontSize: Number(widget.fontSize) })),
    pollInterval: Number(scene.pollInterval),
  });
}

export function reconcileSavedScene(submitted, current, saved, fallbackDate) {
  // The response describes the submitted snapshot; replacing newer edits would silently undo work during POST.
  return sceneKey(submitted, fallbackDate) === sceneKey(current, fallbackDate) ? saved : { ...current, id: saved.id };
}

export function colorInputValue(value) {
  // Native pickers require #rrggbb; project only their display value so loading does not strip saved RGBA/alpha.
  const color = String(value).trim().toLowerCase();
  if (/^#[\da-f]{3,4}$/.test(color)) return '#' + [...color.slice(1, 4)].map(character => character + character).join('');
  if (/^#[\da-f]{6}(?:[\da-f]{2})?$/.test(color)) return color.slice(0, 7);
  const rgb = color.match(/^rgba?\(([^)]+)\)$/);
  if (rgb) {
    const channels = rgb[1].split(',').slice(0, 3).map(channel => { const number = Number.parseFloat(channel); return Math.max(0, Math.min(255, Math.round(channel.trim().endsWith('%') ? number * 255 / 100 : number))); });
    if (channels.length === 3 && channels.every(Number.isFinite)) return '#' + channels.map(channel => channel.toString(16).padStart(2, '0')).join('');
  }
  return color === 'white' ? '#ffffff' : '#000000';
}

export function aspectRatioLabel(width, height) {
  const gcd = (a, b) => b ? gcd(b, a % b) : a;
  const divisor = gcd(width, height);
  return `${width / divisor}:${height / divisor}`;
}
