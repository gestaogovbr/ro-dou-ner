/* Canonical offsets are Unicode code points, matching Python's [start, end). */
(function (root, factory) {
  const helpers = factory();
  if (typeof module === 'object' && module.exports) module.exports = helpers;
  else root.NerPreview = helpers;
})(typeof globalThis === 'undefined' ? this : globalThis, function () {
  'use strict';
  const taxonomy = {
    PERSON: { title: 'Pessoa', color: '#f5d1df' },
    ORGANIZATION: { title: 'Organização', color: '#c5e7ec' },
    LOCATION: { title: 'Local', color: '#d3e6bf' },
    PROCESS_NUMBER: { title: 'Processo', color: '#dbd1fa' },
    IDENTIFIER: { title: 'Identificador', color: '#ffd9b1' },
    DATE: { title: 'Data', color: '#fff1a0' },
    MONEY: { title: 'Valor', color: '#bbdfcc' },
    LEGAL_REFERENCE: { title: 'Referência legal', color: '#cdd9fb' },
  };
  const labelInfo = (label) => taxonomy[label] || { title: String(label), color: '#e2e5e8' };

  function validateMentions(text, mentions) {
    const chars = Array.from(text);
    const valid = [];
    let invalid = 0;
    for (const mention of mentions || []) {
      if (!mention || typeof mention.label !== 'string' || !mention.label
          || !Number.isInteger(mention.start) || !Number.isInteger(mention.end)
          || mention.start < 0 || mention.end <= mention.start || mention.end > chars.length
          || chars.slice(mention.start, mention.end).join('') !== mention.surface) {
        invalid += 1;
      } else valid.push(mention);
    }
    return { chars, valid, invalid };
  }

  function segmentText(text, mentions, visibleLabels = null) {
    const { chars, valid, invalid } = validateMentions(text, mentions);
    const visible = visibleLabels === null ? null : new Set(visibleLabels);
    const events = new Map();
    const eventAt = (position) => {
      if (!events.has(position)) events.set(position, { add: [], remove: [] });
      return events.get(position);
    };
    eventAt(0);
    eventAt(chars.length);
    for (const mention of valid) {
      if (visible && !visible.has(mention.label)) continue;
      eventAt(mention.start).add.push(mention);
      eventAt(mention.end).remove.push(mention);
    }
    const positions = Array.from(events.keys()).sort((a, b) => a - b);
    const active = new Set();
    const segments = [];
    for (let i = 0; i < positions.length - 1; i++) {
      const start = positions[i];
      const end = positions[i + 1];
      const event = events.get(start);
      event.remove.forEach((mention) => active.delete(mention));
      event.add.forEach((mention) => active.add(mention));
      if (end <= start) continue;
      const current = Array.from(active);
      const labels = Array.from(new Set(current.map((mention) => mention.label)));
      const colors = labels.map((label) => labelInfo(label).color);
      const background = colors.length > 1
        ? `linear-gradient(to bottom, ${colors.map((color, index) => `${color} ${index * 100 / colors.length}%, ${color} ${(index + 1) * 100 / colors.length}%`).join(', ')})`
        : colors[0] || 'transparent';
      segments.push({
        start, end, text: chars.slice(start, end).join(''), labels, mentions: current,
        style: { background },
        title: current.map((mention) => `${labelInfo(mention.label).title}: ${mention.surface} [${mention.start}, ${mention.end}) · ${mention.extractor || '—'}`).join('\n'),
      });
    }
    return { segments, valid, invalid };
  }
  return { taxonomy, labelInfo, validateMentions, segmentText };
});
