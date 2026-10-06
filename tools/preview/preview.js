/* Temporary inspection UI. Documents are always rendered as escaped text. */
(function () {
  'use strict';
  const { createApp } = Vue;
  const { labelInfo, validateMentions, segmentText } = NerPreview;
  createApp({
    data: () => ({ items: [], selectedId: null, total: 0, page: 1, pageSize: 10, totalPages: 0,
      hasNext: false, hasPrevious: false, loading: false, error: '', visibleLabels: [],
      focusedMentions: [], jsonOpen: false, requestNumber: 0 }),
    computed: {
      selected() { return this.items.find((item) => item.id === this.selectedId) || null; },
      validMentions() {
        if (!this.selected) return [];
        return validateMentions(this.selected.document.body_text || '', this.selected.document.mentions || []).valid;
      },
      labels() {
        const counts = new Map();
        for (const mention of this.validMentions) counts.set(mention.label, (counts.get(mention.label) || 0) + 1);
        return Array.from(counts, ([label, count]) => ({ label, count }));
      },
      highlightData() {
        if (!this.selected) return { segments: [], invalid: 0 };
        return segmentText(this.selected.document.body_text || '', this.selected.document.mentions || [], this.visibleLabels);
      },
      documentJson() { return JSON.stringify(this.selected?.document || {}, null, 2); },
    },
    methods: {
      info: labelInfo,
      number(value) { return new Intl.NumberFormat('pt-BR').format(value); },
      shortVersion(value) { return value ? String(value).slice(0, 12) : '—'; },
      score(value) { return value === null || value === undefined ? '—' : new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 3 }).format(value); },
      publicationTitle(document) {
        const meta = document.metadata || {};
        return meta.identifica || meta.titulo || meta.title || document.title || document.publication_id || 'Publicação sem título';
      },
      publicationDate(document) {
        const meta = document.metadata || {};
        const value = meta.pubdate || meta.data_publicacao || meta.data || document.completed_at;
        if (!value) return 'Data não informada';
        const day = String(value).slice(0, 10);
        return /^\d{4}-\d{2}-\d{2}$/.test(day) ? day.split('-').reverse().join('/') : day;
      },
      organization(document) { const meta = document.metadata || {}; return meta.artcategory || meta.orgao || meta.category || ''; },
      selectItem(item) {
        this.selectedId = item.id;
        this.focusedMentions = [];
        this.visibleLabels = this.labels.map((entry) => entry.label);
      },
      async loadPage(target) {
        if (!Number.isInteger(target) || target < 1) return;
        const request = ++this.requestNumber;
        this.loading = true;
        this.error = '';
        try {
          const response = await fetch(`/publications?page=${target}&page_size=${this.pageSize}`, { headers: { Accept: 'application/json' } });
          if (!response.ok) throw new Error(`Não foi possível carregar as publicações (HTTP ${response.status}).`);
          const data = await response.json();
          if (!Array.isArray(data.items) || !Number.isInteger(data.total)) throw new Error('A API retornou um formato inesperado.');
          if (request !== this.requestNumber) return;
          this.items = data.items;
          this.total = data.total;
          this.page = data.page;
          this.totalPages = data.total_pages;
          this.hasNext = data.has_next;
          this.hasPrevious = data.has_previous;
          const next = this.items.find((item) => item.id === this.selectedId) || this.items[0];
          if (next) this.selectItem(next);
          else { this.selectedId = null; this.visibleLabels = []; }
        } catch (error) {
          if (request === this.requestNumber) this.error = error.message || 'Não foi possível acessar a API.';
        } finally {
          if (request === this.requestNumber) this.loading = false;
        }
      },
    },
    mounted() { this.loadPage(1); },
  }).mount('#app');
})();
