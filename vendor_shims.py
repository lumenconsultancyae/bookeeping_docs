"""Offline local vendor JS shims served by `agy_service.py` when CDNs are unreachable."""

from __future__ import annotations

CHART_JS_SHIM = """(function(window) {
    class Chart {
        constructor(ctx, config) { this.ctx = ctx; this.config = config || {}; this._renderCanvasPreview(); }
        _renderCanvasPreview() {
            try {
                const canvas = this.ctx && this.ctx.canvas ? this.ctx.canvas : this.ctx;
                if (!canvas || !canvas.getContext) return;
                const parent = canvas.parentElement;
                const w = canvas.width = Math.max(480, (parent && parent.clientWidth ? parent.clientWidth - 48 : 680));
                const h = canvas.height = Math.max(210, (parent && parent.clientHeight ? parent.clientHeight - 48 : 240));
                const c = canvas.getContext('2d'), padL = 56, padR = 24, padT = 36, padB = 34, plotW = w - padL - padR, plotH = h - padT - padB;
                c.clearRect(0, 0, w, h); c.fillStyle = '#ffffff'; c.fillRect(0, 0, w, h); c.strokeStyle = '#e4e7ec'; c.lineWidth = 1;
                for (let g = 0; g <= 4; g++) { const y = padT + (plotH * g) / 4; c.beginPath(); c.moveTo(padL, y); c.lineTo(w - padR, y); c.stroke(); }
                const labels = (this.config.data && this.config.data.labels) || [], datasets = (this.config.data && this.config.data.datasets) || [];
                datasets.forEach((ds, dIdx) => {
                    const lx = w - padR - (datasets.length - dIdx) * 125;
                    c.fillStyle = ds.backgroundColor || (dIdx === 0 ? '#067647' : '#b42318'); c.fillRect(lx, 10, 10, 10);
                    c.fillStyle = '#475467'; c.font = '500 11px Inter, sans-serif'; c.fillText(String(ds.label || (dIdx === 0 ? 'Cash In' : 'Cash Out')), lx + 15, 19);
                });
                const slotW = plotW / Math.max(labels.length, 1), barW = Math.min(28, Math.max(14, Math.floor(slotW / 3.2)));
                labels.forEach((label, idx) => {
                    const xCenter = padL + idx * slotW + slotW / 2;
                    datasets.forEach((ds, dIdx) => {
                        const val = Number((ds.data && ds.data[idx]) || 0), barH = val > 0 ? Math.min(plotH - 12, Math.max(14, Math.log10(val + 10) * 38)) : 6;
                        const bx = xCenter + (dIdx - (datasets.length - 1) / 2) * (barW + 6) - barW / 2;
                        c.fillStyle = ds.backgroundColor || (dIdx === 0 ? '#067647' : '#b42318'); c.fillRect(bx, padT + plotH - barH, barW, barH);
                    });
                    c.fillStyle = '#475467'; c.font = '500 11px Inter, sans-serif'; c.textAlign = 'center'; c.fillText(String(label), xCenter, h - 12);
                });
                c.textAlign = 'start';
            } catch (e) {}
        }
        destroy() {}
        update() { this._renderCanvasPreview(); }
    }
    window.Chart = Chart;
})(window);"""

PDF_JS_SHIM = """(function(window) {
    const pdfjsLib = {
        version: '3.11.174',
        GlobalWorkerOptions: { workerSrc: '' },
        getDocument: function() {
            return { promise: Promise.resolve({ numPages: 1, getPage: function(pageNum) {
                return Promise.resolve({
                    getViewport: function(opts) { return { width: 600, height: 800, scale: (opts && opts.scale) || 1 }; },
                    render: function(renderCtx) {
                        try { if (renderCtx && renderCtx.canvasContext) {
                            const ctx = renderCtx.canvasContext; ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, 600, 800);
                            ctx.fillStyle = '#0f172a'; ctx.font = '16px sans-serif'; ctx.fillText('PDF Document Page ' + pageNum, 40, 60);
                        } } catch (e) {}
                        return { promise: Promise.resolve() };
                    },
                    getTextContent: function() { return Promise.resolve({ items: [] }); }
                });
            } }) };
        }
    };
    window.pdfjsLib = pdfjsLib; window['pdfjs-dist/build/pdf'] = pdfjsLib;
})(window);"""
