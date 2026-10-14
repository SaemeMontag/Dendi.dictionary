// Формы русских слов для «Перевода фразы».
// Вход (stdin): JSON-массив русских слов. Выход (stdout): JSON {лемма: "общее_начало|окончание1,окончание2,…"}.
// Все формы каждой леммы из словаря OpenCorpora (через Az.js), кроме причастий; ё заменяется на е.
const path = require('path');
const Az = require(path.join(__dirname, 'vendor/az/az.js'));

const norm = s => s.toLowerCase().replace(/ё/g, 'е');
const SKIP_POS = new Set(['PRTF', 'PRTS']);

let input = '';
process.stdin.on('data', d => input += d);
process.stdin.on('end', () => {
  const words = [...new Set(JSON.parse(input).map(norm))].sort();
  Az.Morph.init(path.join(__dirname, 'vendor/az/dicts'), err => {
    if (err) { console.error(String(err)); process.exit(1); }
    const lex = new Map();
    for (const w of words) {
      let parses = [];
      try { parses = Az.Morph(w) || []; } catch (_) { parses = []; }
      for (const p of parses) {
        if (!p || typeof p.formCnt !== 'number') continue;          // только словарные разборы
        const lemma = norm(p.normalize().word);
        if (!lex.has(lemma)) lex.set(lemma, new Set([lemma]));
        const set = lex.get(lemma);
        set.add(w);
        for (let i = 0; i < p.formCnt; i++) {
          const f = p.inflect(i);
          if (!f || !f.word || (f.tag && SKIP_POS.has(f.tag.POS))) continue;
          const fw = norm(f.word);
          if (fw.length < 2 && fw !== lemma) continue;
          set.add(fw);
        }
      }
    }
    const out = {};
    for (const lemma of [...lex.keys()].sort()) {
      const forms = [...lex.get(lemma)].sort();
      let pre = forms[0];
      for (const f of forms) while (!f.startsWith(pre)) pre = pre.slice(0, -1);
      out[lemma] = pre + '|' + forms.map(f => f.slice(pre.length)).join(',');
    }
    process.stdout.write(JSON.stringify(out));
  });
});
