const test = require('node:test');
const assert = require('node:assert/strict');
const { segmentText, validateMentions } = require('../../tools/preview/highlights.js');

const mention = (label, surface, start, end) => ({ label, surface, start, end, extractor: 'test', score: 0.9 });

test('Python code-point offsets highlight the correct entity after an emoji', () => {
  const text = '😀 Ana é de Goiânia.';
  const result = segmentText(text, [mention('PERSON', 'Ana', 2, 5), mention('LOCATION', 'Goiânia', 11, 18)]);
  assert.equal(result.invalid, 0);
  assert.equal(result.segments.map((segment) => segment.text).join(''), text);
  assert.deepEqual(result.segments.filter((segment) => segment.labels.length).map((segment) => segment.text), ['Ana', 'Goiânia']);
});

test('nested and crossing mentions retain every active entity on each segment', () => {
  const text = 'Universidade de São Paulo';
  const org = mention('ORGANIZATION', text, 0, 25);
  const city = mention('LOCATION', 'São Paulo', 16, 25);
  const person = mention('PERSON', 'de São', 13, 19);
  const result = segmentText(text, [org, city, person]);
  assert.equal(result.invalid, 0);
  assert.equal(result.segments.map((segment) => segment.text).join(''), text);
  const crossing = result.segments.find((segment) => segment.start === 16);
  assert.deepEqual(new Set(crossing.labels), new Set(['ORGANIZATION', 'LOCATION', 'PERSON']));
  assert.equal(crossing.mentions.length, 3);
  assert.match(crossing.style.background, /^linear-gradient/);
  assert.match(crossing.title, /Organização/);
  assert.match(crossing.title, /Local/);
  assert.match(crossing.title, /Pessoa/);
});

test('adjacent intervals use half-open ends without carrying a previous entity', () => {
  const result = segmentText('AnaRio', [mention('PERSON', 'Ana', 0, 3), mention('LOCATION', 'Rio', 3, 6)]);
  assert.deepEqual(result.segments.map((segment) => segment.labels), [['PERSON'], ['LOCATION']]);
});

test('label filters remove highlights while preserving the complete original text', () => {
  const text = 'Ana em Rio';
  const mentions = [mention('PERSON', 'Ana', 0, 3), mention('LOCATION', 'Rio', 7, 10)];
  const one = segmentText(text, mentions, ['LOCATION']);
  assert.deepEqual(one.segments.filter((segment) => segment.labels.length).map((segment) => segment.text), ['Rio']);
  const none = segmentText(text, mentions, []);
  assert.deepEqual(none.segments.map((segment) => segment.text), [text]);
});

test('invalid, mismatched, negative, fractional and out-of-range boundaries are counted and excluded', () => {
  const bad = [null, mention('PERSON', 'Ana', -1, 3), mention('PERSON', 'Ana', 0.5, 3),
    mention('PERSON', 'Ana', 0, 100), mention('PERSON', 'Bia', 0, 3), mention('PERSON', '', 0, 0)];
  const result = segmentText('Ana', [...bad, mention('PERSON', 'Ana', 0, 3)]);
  assert.equal(result.invalid, bad.length);
  assert.equal(result.valid.length, 1);
  assert.equal(result.segments[0].text, 'Ana');
});

test('emoji inside the entity and combining characters retain exact original surfaces', () => {
  const text = '👩‍🔬 Ana\u0301';
  const result = validateMentions(text, [mention('PERSON', text, 0, Array.from(text).length)]);
  assert.equal(result.valid.length, 1);
  assert.equal(result.invalid, 0);
  assert.equal(segmentText(text, result.valid).segments[0].text, text);
});

test('HTML-like indexed text remains literal text for escaped Vue interpolation', () => {
  const text = '<img src=x onerror="globalThis.pwned=true"> & Ana';
  const offset = Array.from(text).length - 3;
  const result = segmentText(text, [mention('PERSON', 'Ana', offset, offset + 3)]);
  assert.equal(result.segments[0].text, text.slice(0, -3));
  assert.equal(result.segments.map((segment) => segment.text).join(''), text);
});

test('empty text and absent mentions yield an empty or unchanged reading surface', () => {
  assert.deepEqual(segmentText('', null).segments, []);
  assert.equal(segmentText('sem entidades', null).segments[0].text, 'sem entidades');
});

test('coincident mentions with different labels preserve both labels and separate origins', () => {
  const result = segmentText('Rio', [mention('PERSON', 'Rio', 0, 3), { ...mention('LOCATION', 'Rio', 0, 3), extractor: 'rules' }]);
  assert.equal(result.segments[0].mentions.length, 2);
  assert.deepEqual(result.segments[0].labels, ['PERSON', 'LOCATION']);
  assert.match(result.segments[0].title, /test/);
  assert.match(result.segments[0].title, /rules/);
});
