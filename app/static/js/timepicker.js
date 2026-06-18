class TimePicker {
    constructor(containerId, options = {}) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        if (!this.container) return;

        this.hours = 0;
        this.minutes = 0;
        this.mode = 'hour';
        this.onChange = options.onChange || null;
        this._pop = null;
        this._outsideClick = this._onOutside.bind(this);

        if (options.initialValue) this._parse(options.initialValue);
        this._build();
    }

    getValue() {
        return `${String(this.hours).padStart(2,'0')}:${String(this.minutes).padStart(2,'0')}`;
    }

    setValue(hhmm) {
        this._parse(hhmm);
        this._refreshBtn();
    }

    _parse(hhmm) {
        if (!hhmm) return;
        const [h, m] = hhmm.split(':').map(Number);
        this.hours   = isNaN(h) ? 0 : Math.min(23, Math.max(0, h));
        this.minutes = isNaN(m) ? 0 : Math.min(59, Math.max(0, m));
    }

    _build() {
        this.container.innerHTML = '';
        this.container.className = 'tp-widget';
        this._btn = document.createElement('button');
        this._btn.type = 'button';
        this._btn.className = 'tp-display';
        this._btn.addEventListener('click', e => { e.stopPropagation(); this._toggle(); });
        this.container.appendChild(this._btn);
        this._refreshBtn();
    }

    _refreshBtn() {
        const hh = String(this.hours).padStart(2,'0');
        const mm = String(this.minutes).padStart(2,'0');
        this._btn.innerHTML =
            `<span class="tp-hh">${hh}</span><span class="tp-sep">:</span><span class="tp-mm">${mm}</span>`;
    }

    _toggle() { this._pop ? this._close() : this._open(); }

    _open() {
        this.mode = 'hour';
        const pop = document.createElement('div');
        pop.className = 'tp-popover';
        const id = this.containerId;
        pop.innerHTML = `
            <div class="tp-digits">
                <input class="tp-d" id="${id}__d0" maxlength="1" inputmode="numeric" placeholder="H" autocomplete="off">
                <input class="tp-d" id="${id}__d1" maxlength="1" inputmode="numeric" placeholder="H" autocomplete="off">
                <span class="tp-dsep">:</span>
                <input class="tp-d" id="${id}__d2" maxlength="1" inputmode="numeric" placeholder="M" autocomplete="off">
                <input class="tp-d" id="${id}__d3" maxlength="1" inputmode="numeric" placeholder="M" autocomplete="off">
            </div>
            <div class="tp-modes">
                <button type="button" class="tp-mode-btn active" id="${id}__hr">HOUR</button>
                <button type="button" class="tp-mode-btn" id="${id}__mn">MIN</button>
            </div>
            <div class="tp-clock" id="${id}__clock"></div>`;
        this._pop = pop;
        this.container.appendChild(pop);
        this._syncDigits();
        this._hookDigits();
        this._hookModes();
        this._drawClock();
        setTimeout(() => document.addEventListener('click', this._outsideClick), 0);
    }

    _close() {
        if (this._pop) { this._pop.remove(); this._pop = null; }
        document.removeEventListener('click', this._outsideClick);
    }

    _onOutside(e) { if (!this.container.contains(e.target)) this._close(); }

    _d(i) { return document.getElementById(`${this.containerId}__d${i}`); }

    _syncDigits() {
        const hh = String(this.hours).padStart(2,'0');
        const mm = String(this.minutes).padStart(2,'0');
        [hh[0], hh[1], mm[0], mm[1]].forEach((v, i) => { const el = this._d(i); if (el) el.value = v; });
    }

    _hookDigits() {
        for (let i = 0; i < 4; i++) {
            const inp = this._d(i);
            if (!inp) continue;
            inp.addEventListener('keydown', e => {
                if (e.key === 'Backspace' && !inp.value && i > 0) {
                    const prev = this._d(i - 1);
                    if (prev) { prev.value = ''; prev.focus(); }
                }
            });
            inp.addEventListener('input', () => {
                inp.value = inp.value.replace(/[^0-9]/g, '').slice(-1);
                this._applyDigits();
                if (inp.value && i < 3) { const next = this._d(i + 1); if (next) next.focus(); }
            });
        }
    }

    _applyDigits() {
        const v = [0,1,2,3].map(i => { const el = this._d(i); return el && el.value !== '' ? parseInt(el.value) : null; });
        if (v[0] !== null && v[1] !== null) {
            const h = v[0] * 10 + v[1];
            if (h <= 23) this.hours = h;
        }
        if (v[2] !== null && v[3] !== null) {
            const m = v[2] * 10 + v[3];
            if (m <= 59) this.minutes = m;
        }
        this._refreshBtn();
        this._drawClock();
        if (this.onChange) this.onChange(this.getValue());
    }

    _hookModes() {
        const hr = document.getElementById(`${this.containerId}__hr`);
        const mn = document.getElementById(`${this.containerId}__mn`);
        hr?.addEventListener('click', e => { e.stopPropagation(); this.mode = 'hour';   this._drawClock(); });
        mn?.addEventListener('click', e => { e.stopPropagation(); this.mode = 'minute'; this._drawClock(); });
    }

    _polar(deg, r, cx, cy) {
        const rad = (deg - 90) * Math.PI / 180;
        return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
    }

    _drawClock() {
        const wrap = document.getElementById(`${this.containerId}__clock`);
        if (!wrap) return;

        const isHour = this.mode === 'hour';
        const S = 220, cx = S / 2, cy = S / 2;
        const outerR = 88, innerR = 58;
        const ns = 'http://www.w3.org/2000/svg';

        const svg = document.createElementNS(ns, 'svg');
        svg.setAttribute('viewBox', `0 0 ${S} ${S}`);
        svg.setAttribute('width', S);
        svg.setAttribute('height', S);
        svg.style.cursor = 'pointer';

        // Background circle
        const bg = document.createElementNS(ns, 'circle');
        bg.setAttribute('cx', cx); bg.setAttribute('cy', cy); bg.setAttribute('r', S / 2 - 2);
        bg.setAttribute('fill', '#1e2040');
        svg.appendChild(bg);

        // Hand
        let handAngle;
        if (isHour) {
            const h = this.hours;
            handAngle = h === 0 ? 0 : h <= 12 ? h * 30 : (h - 12) * 30;
        } else {
            handAngle = (this.minutes / 60) * 360;
        }
        const handR = isHour
            ? (this.hours >= 1 && this.hours <= 12 ? outerR : innerR) - 14
            : outerR - 14;
        const handTip = this._polar(handAngle, handR, cx, cy);

        const line = document.createElementNS(ns, 'line');
        line.setAttribute('x1', cx); line.setAttribute('y1', cy);
        line.setAttribute('x2', handTip.x); line.setAttribute('y2', handTip.y);
        line.setAttribute('stroke', '#7e8ce0'); line.setAttribute('stroke-width', '2');
        svg.appendChild(line);

        const dot = document.createElementNS(ns, 'circle');
        dot.setAttribute('cx', cx); dot.setAttribute('cy', cy); dot.setAttribute('r', 3);
        dot.setAttribute('fill', '#7e8ce0');
        svg.appendChild(dot);

        // Numbers
        if (isHour) {
            // Outer ring: 12, 1–11
            for (let slot = 0; slot < 12; slot++) {
                const h = slot === 0 ? 12 : slot;
                this._addNum(svg, ns, h, this._polar(slot * 30, outerR, cx, cy), this.hours === h, 13);
            }
            // Inner ring: 0, 13–23
            const inner = [0, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23];
            for (let slot = 0; slot < 12; slot++) {
                const h = inner[slot];
                this._addNum(svg, ns, h, this._polar(slot * 30, innerR, cx, cy), this.hours === h, 10);
            }
        } else {
            for (let slot = 0; slot < 12; slot++) {
                const m = slot * 5;
                const label = String(m).padStart(2, '0');
                this._addNum(svg, ns, label, this._polar(slot * 30, outerR, cx, cy), this.minutes === m, 13);
            }
        }

        svg.addEventListener('click', e => this._clockClick(e, cx, cy, outerR, innerR, isHour, S));
        wrap.innerHTML = '';
        wrap.appendChild(svg);

        // Sync mode button active states
        document.getElementById(`${this.containerId}__hr`)?.classList.toggle('active', isHour);
        document.getElementById(`${this.containerId}__mn`)?.classList.toggle('active', !isHour);
    }

    _addNum(svg, ns, label, pos, selected, fontSize) {
        if (selected) {
            const bg = document.createElementNS(ns, 'circle');
            bg.setAttribute('cx', pos.x); bg.setAttribute('cy', pos.y);
            bg.setAttribute('r', fontSize >= 13 ? 14 : 11);
            bg.setAttribute('fill', '#7e8ce0');
            svg.appendChild(bg);
        }
        const txt = document.createElementNS(ns, 'text');
        txt.setAttribute('x', pos.x); txt.setAttribute('y', pos.y);
        txt.setAttribute('text-anchor', 'middle');
        txt.setAttribute('dominant-baseline', 'central');
        txt.setAttribute('fill', selected ? '#fff' : '#b8b8d1');
        txt.setAttribute('font-size', fontSize);
        txt.setAttribute('font-family', 'system-ui, sans-serif');
        txt.textContent = label;
        svg.appendChild(txt);
    }

    _clockClick(e, cx, cy, outerR, innerR, isHour, S) {
        const rect = e.currentTarget.getBoundingClientRect();
        const sx = S / rect.width, sy = S / rect.height;
        const x = (e.clientX - rect.left) * sx - cx;
        const y = (e.clientY - rect.top)  * sy - cy;
        const dist = Math.sqrt(x * x + y * y);

        let angle = Math.atan2(y, x) * 180 / Math.PI + 90;
        if (angle < 0) angle += 360;
        const slot = Math.round(angle / 30) % 12;

        if (isHour) {
            if (dist < (outerR + innerR) / 2) {
                this.hours = [0, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23][slot];
            } else {
                this.hours = slot === 0 ? 12 : slot;
            }
            this.mode = 'minute';
            this._refreshBtn();
            this._syncDigits();
            this._drawClock();
        } else {
            this.minutes = slot * 5;
            this._refreshBtn();
            this._syncDigits();
            if (this.onChange) this.onChange(this.getValue());
            this._close();
            return;
        }
        if (this.onChange) this.onChange(this.getValue());
    }
}
