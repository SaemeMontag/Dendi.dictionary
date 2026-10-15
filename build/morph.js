// Формы русских слов для «Перевода фразы».
// Вход (stdin): JSON-массив русских слов.
// Выход (stdout): JSON {
//   lemmas: {лемма: "общее_начало|окончание1,окончание2,…|признаки1,признаки2,…"},  // признаки: номера в tags через «.»
//   tags:   ["NOUN femn sing gent", …],                                           // часть речи и нужные граммемы
//   forms:  {неоднозначная_форма: {лемма: оценка}}                                 // только формы с ≥2 леммами
// }
// Все формы каждой леммы из словаря OpenCorpora (через Az.js), кроме причастий; ё заменяется на е.
const path = require('path');
const Az = require(path.join(__dirname, 'vendor/az/az.js'));

const norm = s => s.toLowerCase().replace(/ё/g, 'е');
const SKIP_POS = new Set(['PRTF', 'PRTS']);
const KEEP = new Set(['Apro', 'Poss', 'nomn', 'gent', 'datv', 'accs', 'ablt', 'loct', 'voct', 'sing', 'plur',
  'masc', 'femn', 'neut', 'ms-f', 'impr', 'indc', 'past', 'pres', 'futr', '1per', '2per', '3per', 'Fixd', 'Pltm', 'Sgtm']);
const ALIAS = { gen2: 'gent', gen1: 'gent', acc2: 'accs', loc2: 'loct', loc1: 'loct' };

function tagString(tag) {
  const parts = String(tag).split(/[ ,]+/).map(g => ALIAS[g] || g);
  const pos = tag.POS || parts[0];
  return [pos, ...parts.filter(g => KEEP.has(g))].filter((g, i, a) => a.indexOf(g) === i).join(' ');
}

let input = '';
process.stdin.on('data', d => input += d);
process.stdin.on('end', () => {
  const words = [...new Set(JSON.parse(input).map(norm))].sort();
  Az.Morph.init(path.join(__dirname, 'vendor/az/dicts'), err => {
    if (err) { console.error(String(err)); process.exit(1); }
    // 1. леммы словаря и все их формы
    const lex = new Map();
    for (const w of words) {
      let parses = [];
      try { parses = Az.Morph(w) || []; } catch (_) { parses = []; }
      for (const p of parses) {
        if (!p || typeof p.formCnt !== 'number') continue;
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
    // 2. признаки каждой формы (по разбору самой формы) и оценки прочтений
    const tags = [], tagIdx = new Map();
    const tid = t => { if (!tagIdx.has(t)) { tagIdx.set(t, tags.length); tags.push(t); } return tagIdx.get(t); };
    const formTags = new Map();     // форма → Map(лемма → Set(номер признаков))
    const formScore = new Map();    // форма → Map(лемма → оценка)
    const allForms = new Set(); lex.forEach(s => s.forEach(f => allForms.add(f)));
    for (const f of [...allForms].sort()) {
      let parses = [];
      try { parses = Az.Morph(f) || []; } catch (_) { parses = []; }
      for (const p of parses) {
        if (!p || typeof p.formCnt !== 'number' || !p.tag || SKIP_POS.has(p.tag.POS)) continue;
        const lemma = norm(p.normalize().word);
        if (!lex.has(lemma) || !lex.get(lemma).has(f)) continue;
        if (!formTags.has(f)) { formTags.set(f, new Map()); formScore.set(f, new Map()); }
        const tm = formTags.get(f), sm = formScore.get(f);
        if (!tm.has(lemma)) tm.set(lemma, new Set());
        tm.get(lemma).add(tid(tagString(p.tag)));
        sm.set(lemma, (sm.get(lemma) || 0) + (p.score || 0));
      }
    }
    const lemmasOut = {};
    for (const lemma of [...lex.keys()].sort()) {
      const forms = [...lex.get(lemma)].sort();
      let pre = forms[0];
      for (const f of forms) while (!f.startsWith(pre)) pre = pre.slice(0, -1);
      const tg = forms.map(f => [...((formTags.get(f) || new Map()).get(lemma) || [])].sort((a, b) => a - b).map(n => n.toString(36)).join('.'));
      lemmasOut[lemma] = pre + '|' + forms.map(f => f.slice(pre.length)).join(',') + '|' + tg.join(',');
    }
    const formsOut = {};
    for (const [f, sm] of [...formScore.entries()].sort()) {
      if (sm.size < 2) continue;
      const o = {}; [...sm.entries()].sort().forEach(([l, s]) => o[l] = Math.round(s * 1000) / 1000);
      formsOut[f] = o;
    }
    process.stdout.write(JSON.stringify({ lemmas: lemmasOut, tags, forms: formsOut }));
  });
});
