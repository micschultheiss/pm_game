/* hallu-engine.js — ASCII block-font renderer + terminal boot animator
 * Exposes window.HALLU = { FONT, textToGrid, mount }.
 * Plain JS (no React) so it can drive any DOM root; each mount() is
 * self-contained and returns a cleanup fn (design_canvas re-mounts the
 * same JSX in its focus overlay, so multiple live instances must coexist).
 */
(function () {
  // ── 5×7 bitmap glyphs (only the letters HALLUCINATION + INC. need) ──────
  const G = {
    A: ['.###.', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
    C: ['.####', '#....', '#....', '#....', '#....', '#....', '.####'],
    H: ['#...#', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
    I: ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '#####'],
    L: ['#....', '#....', '#....', '#....', '#....', '#....', '#####'],
    N: ['#...#', '##..#', '#.#.#', '#.#.#', '#.#.#', '#..##', '#...#'],
    O: ['.###.', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
    T: ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '..#..'],
    U: ['#...#', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
    '.': ['.....', '.....', '.....', '.....', '.....', '.##..', '.##..'],
  };
  const ROWS = 7;

  // text → array of 7 strings of '#'/'.' (1-col gap between glyphs, 3-col space)
  function textToGrid(text) {
    const out = ['', '', '', '', '', '', ''];
    const chars = text.toUpperCase().split('');
    chars.forEach((ch, i) => {
      if (ch === ' ') {
        for (let r = 0; r < ROWS; r++) out[r] += '...';
      } else {
        const g = G[ch] || G['.'];
        for (let r = 0; r < ROWS; r++) out[r] += g[r];
      }
      if (i < chars.length - 1) for (let r = 0; r < ROWS; r++) out[r] += '.';
    });
    return out;
  }

  // grid → string, mapping fill / empty chars; reveal limits columns (sweep)
  function gridToText(grid, fill, empty, reveal) {
    const cols = reveal == null ? grid[0].length : reveal;
    return grid
      .map((row) => row.slice(0, cols).replace(/#/g, fill).replace(/\./g, empty))
      .join('\n');
  }

  // dotted-leader boot line: "label ........ STATUS"
  function leader(label, status, w) {
    const dots = Math.max(2, w - label.length - status.length - 2);
    return { label, dots: '.'.repeat(dots), status };
  }

  // ── one-time global stylesheet (palette comes from per-stage CSS vars) ──
  function injectStyles() {
    if (document.getElementById('hi-styles')) return;
    const s = document.createElement('style');
    s.id = 'hi-styles';
    s.textContent = `
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
.hi-stage{position:absolute;inset:0;overflow:hidden;background:var(--hi-bg);
  color:var(--hi-fg);font-family:'JetBrains Mono','IBM Plex Mono',ui-monospace,monospace;
  -webkit-font-smoothing:none;display:flex;align-items:center;justify-content:center;}
.hi-stage *{box-sizing:border-box;}
.hi-inner{position:relative;width:100%;height:100%;display:flex;align-items:center;justify-content:center;}

/* boot console */
.hi-console{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  width:min(78%,860px);transition:opacity .45s ease,transform .55s cubic-bezier(.4,0,.2,1);}
.hi-log{margin:0;font-size:17px;line-height:1.95;white-space:pre-wrap;letter-spacing:.5px;}
.hi-log .ln{display:flex;align-items:baseline;opacity:0;animation:hiLn .01s forwards;}
.hi-log .lb{color:var(--hi-fg);opacity:.92;}
.hi-log .ld{flex:1;color:var(--hi-fg);opacity:.28;overflow:hidden;white-space:nowrap;margin:0 .5ch;}
.hi-ok{color:var(--hi-accent);font-weight:700;}
.hi-skip{color:var(--hi-warn);font-weight:700;}
.hi-num{color:var(--hi-fg);opacity:.6;}
@keyframes hiLn{to{opacity:1;}}

/* logo block */
.hi-logo{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  display:flex;flex-direction:column;align-items:center;opacity:0;transition:opacity .5s ease;}
.hi-logo.show{opacity:1;}
.hi-wordbox{padding:0;}
.hi-word,.hi-inc{margin:0;font-weight:700;white-space:pre;line-height:1.02;
  font-size:var(--hi-word-size);letter-spacing:0;}
.hi-inc{align-self:flex-end;margin-top:.5em;opacity:.95;}

/* glow / 3d / glitch / dot matrix variants keyed on data-effect */
.hi-stage[data-effect="phosphor"] .hi-word,
.hi-stage[data-effect="phosphor"] .hi-inc{
  text-shadow:0 0 6px var(--hi-glow),0 0 18px var(--hi-glow);}
.hi-stage[data-effect="amber3d"] .hi-word,
.hi-stage[data-effect="amber3d"] .hi-inc{
  color:var(--hi-fg);
  text-shadow:1px 1px var(--hi-dim),2px 2px var(--hi-dim),3px 3px var(--hi-dim),
    4px 4px var(--hi-dim),5px 5px rgba(0,0,0,.55),0 0 14px var(--hi-glow);}
.hi-stage[data-effect="glitch"] .hi-word,
.hi-stage[data-effect="glitch"] .hi-inc{
  text-shadow:-3px 0 0 var(--hi-r),3px 0 0 var(--hi-b);
  animation:hiGlitch 3.4s steps(1) infinite;}
.hi-stage[data-effect="box"] .hi-wordbox{
  border:3px double var(--hi-accent);padding:.5em .8em .35em;
  box-shadow:0 0 0 1px rgba(255,255,255,.04),inset 0 0 30px rgba(0,0,0,.4);}
.hi-stage[data-effect="box"] .hi-inc{margin-top:.55em;}
.hi-stage[data-effect="dot"] .hi-word,
.hi-stage[data-effect="dot"] .hi-inc{
  text-shadow:0 0 5px var(--hi-glow);letter-spacing:.04em;}
@keyframes hiGlitch{
  0%,92%,100%{transform:translate(0,0);}
  93%{transform:translate(-3px,1px);}
  95%{transform:translate(2px,-1px);}
  97%{transform:translate(-1px,0);}}

/* footer */
.hi-footer{position:absolute;left:0;right:0;bottom:0;padding:0 6% 4.2%;
  display:flex;flex-direction:column;align-items:center;gap:1.1em;opacity:0;
  transition:opacity .6s ease .15s;text-align:center;}
.hi-footer.show{opacity:1;}
.hi-tag{font-size:18px;letter-spacing:3px;text-transform:uppercase;
  color:var(--hi-fg);opacity:.78;}
.hi-prompt{font-size:16px;letter-spacing:1.8px;color:var(--hi-accent);
  font-weight:600;}
.hi-prompt .cur{animation:hiBlink 1.05s steps(1) infinite;}
.hi-copy{font-size:12.5px;letter-spacing:.6px;color:var(--hi-fg);
  opacity:.42;max-width:64ch;line-height:1.6;}
@keyframes hiBlink{0%,49%{opacity:1;}50%,100%{opacity:0;}}

/* CRT overlays */
.hi-scan{position:absolute;inset:0;pointer-events:none;z-index:6;
  background:repeating-linear-gradient(0deg,rgba(0,0,0,.32) 0,rgba(0,0,0,.32) 1px,transparent 1px,transparent 3px);
  mix-blend-mode:multiply;opacity:.55;}
.hi-vig{position:absolute;inset:0;pointer-events:none;z-index:7;
  background:radial-gradient(120% 120% at 50% 50%,transparent 55%,rgba(0,0,0,.55) 100%);}
.hi-flick{position:absolute;inset:0;pointer-events:none;z-index:8;background:var(--hi-fg);
  opacity:0;mix-blend-mode:overlay;animation:hiFlick 7s steps(1) infinite;}
@keyframes hiFlick{0%,97%,100%{opacity:0;}97.5%{opacity:.03;}98.5%{opacity:.05;}}
`;
    document.head.appendChild(s);
  }

  // ── mount a full splash onto root with a looping boot→reveal cycle ──────
  function mount(root, cfg) {
    injectStyles();
    const fill = cfg.fill || '█';
    const empty = cfg.empty || ' ';
    const grid = textToGrid('HALLUCINATION');
    const incGrid = textToGrid('INC.');

    const styleVars = `--hi-bg:${cfg.bg};--hi-fg:${cfg.fg};--hi-dim:${cfg.dim};` +
      `--hi-accent:${cfg.accent};--hi-warn:${cfg.warn};--hi-glow:${cfg.glow || cfg.accent};` +
      `--hi-r:${cfg.r || '#ff2d55'};--hi-b:${cfg.b || '#21e6c1'};--hi-word-size:${cfg.wordSize}`;

    root.innerHTML = `
      <div class="hi-stage" data-effect="${cfg.effect}" style="${styleVars}">
        <div class="hi-inner">
          <div class="hi-console"><pre class="hi-log"></pre></div>
          <div class="hi-logo">
            <div class="hi-wordbox"><pre class="hi-word"></pre></div>
            <pre class="hi-inc"></pre>
          </div>
          <div class="hi-footer">
            <div class="hi-tag">${cfg.tagline}</div>
            <div class="hi-prompt">${cfg.prompt} <span class="cur">▮</span></div>
            <div class="hi-copy">${cfg.copy}</div>
          </div>
        </div>
        ${cfg.scan ? '<div class="hi-scan"></div><div class="hi-flick"></div>' : ''}
        ${cfg.vignette ? '<div class="hi-vig"></div>' : ''}
      </div>`;

    const log = root.querySelector('.hi-log');
    const consoleEl = root.querySelector('.hi-console');
    const logo = root.querySelector('.hi-logo');
    const word = root.querySelector('.hi-word');
    const inc = root.querySelector('.hi-inc');
    const footer = root.querySelector('.hi-footer');

    inc.textContent = gridToText(incGrid, fill, empty);

    const W = 56;
    const lines = cfg.boot.map((l) => leader(l[0], l[1], W).label && { ...leader(l[0], l[1], W), type: l[2] });

    let timers = [];
    let raf = 0;
    let killed = false;
    const after = (ms, fn) => { const t = setTimeout(() => { if (!killed) fn(); }, ms); timers.push(t); };

    function reset() {
      log.innerHTML = '';
      word.textContent = '';
      consoleEl.style.opacity = '1';
      consoleEl.style.transform = 'translate(-50%,-50%)';
      logo.classList.remove('show');
      footer.classList.remove('show');
    }

    function statusSpan(type, status) {
      const cls = type === 'skip' ? 'hi-skip' : type === 'num' ? 'hi-num' : 'hi-ok';
      return `<span class="${cls}">${status}</span>`;
    }

    function runCycle() {
      reset();
      let d = 240;
      lines.forEach((ln, i) => {
        after(d, () => {
          const div = document.createElement('div');
          div.className = 'ln';
          div.innerHTML = `<span class="lb">${ln.label}</span>` +
            `<span class="ld">${ln.dots}</span>` + statusSpan(ln.type, ln.status);
          log.appendChild(div);
        });
        d += 215 + (i === lines.length - 1 ? 260 : 0);
      });

      // reveal: fade console up, sweep the wordmark in by columns
      after(d + 360, () => {
        consoleEl.style.opacity = '0';
        consoleEl.style.transform = 'translate(-50%,-72%)';
        logo.classList.add('show');
        const total = grid[0].length;
        let c = 0;
        const step = () => {
          if (killed) return;
          c = Math.min(total, c + 2);
          word.textContent = gridToText(grid, fill, empty, c);
          if (c < total) raf = requestAnimationFrame(step);
          else after(420, () => footer.classList.add('show'));
        };
        raf = requestAnimationFrame(step);
      });

      // hold, then loop — unless cfg.loop === false (one-shot: settle on the logo)
      if (cfg.loop !== false) after(d + 360 + 900 + 7200, runCycle);
    }

    runCycle();

    return function cleanup() {
      killed = true;
      timers.forEach(clearTimeout);
      cancelAnimationFrame(raf);
    };
  }

  window.HALLU = { FONT: G, textToGrid, gridToText, mount };
})();
