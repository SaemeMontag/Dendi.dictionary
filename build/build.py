"""Сборка сайта «Словарь денди» из хранилища Obsidian (только чтение).

Использование:
  python3 build.py <папка хранилища> <страница.html> <выход.html> [--site <папка> --base <URL>]

<страница.html> — страница-фрагмент для claude.ai (данные в ней заменяются) или шаблон с __DATA__.
--site: дополнительно собрать полноценный сайт для GitHub Pages в <папке>.

Что читается из хранилища и что нет — см. vault.py (редакторские заметки не открываются).
Код выхода: 0 — собрано (STATUS CHANGED или UNCHANGED); 2 — хранилище не прошло проверки
(STATUS FAILED), ничего не записано, публиковать нельзя. Строки WARNING публикации не мешают.
"""
import re, json, sys, os, datetime, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vault

args = sys.argv[1:]
site_dir = base_url = None
if '--site' in args:
    i = args.index('--site'); site_dir = args[i + 1]; del args[i:i + 2]
if '--base' in args:
    i = args.index('--base'); base_url = args[i + 1].rstrip('/') + '/'; del args[i:i + 2]
src_path, page_path, out = args[0], args[1], args[2]


def fail(msgs):
    print('STATUS FAILED')
    for m in msgs[:40]: print(' -', m)
    sys.exit(2)


if not os.path.isdir(src_path):
    fail([f'{src_path} — не папка хранилища'])
try:
    data, problems, warnings = vault.build_data(src_path)
except vault.VaultError as err:
    fail([f'хранилище: {err}'])

# ---------- морфология русских слов (OpenCorpora через Az.js, см. build/vendor/az) ----------

def ru_vocab(d):
    words = set()
    def add(t):
        words.update(w.lower() for w in re.findall(r'[А-Яа-яЁё]+', re.sub(r'⟦[a-z]:[^|]*\|', ' ', t or '')))
    for e in d['entries']:
        add(re.sub(r'\(.*?\)', ' ', e['title']))
        for x in [x for v in e['variants'] for x in v['examples']] + e.get('linked', []):
            add(x.get('lit')); add(x.get('pub'))
            for seg in (x.get('parse') or '').split(';'):
                mm = re.match(r'^\s*(.+?) — (.+)$', seg)
                if mm: add(re.split(r'[,(]', mm[2])[0])
    return sorted(words)


def ru_morph(d):
    try:
        r = subprocess.run(['node', os.path.join(HERE, 'morph.js')], input=json.dumps(ru_vocab(d), ensure_ascii=False),
                           capture_output=True, text=True, timeout=900)
    except Exception as err:
        return None, f'морфология не собрана ({err})'
    if r.returncode != 0:
        return None, 'морфология не собрана: ' + (r.stderr or '').strip()[:200]
    return json.loads(r.stdout), None


ru, err = ru_morph(data)
if ru:
    data['ru'] = ru['lemmas']; data['rutags'] = ru['tags']; data['rux'] = ru['forms']
else:
    warnings.append(err)

# ---------- проверки и итог ----------

if len(data['entries']) < 100: problems.append(f'статей только {len(data["entries"])}')
if not data['sources']: problems.append('источники не распознаны')
if not data['grammar']: problems.append('грамматика не распознана')
pids = {x['pid'] for e in data['entries'] for x in [x for v in e['variants'] for x in v['examples']] + e['linked']}
E = data['entries']
summary = {'entries': len(E), 'swadesh': sum(e['kind'] == 'swadesh' for e in E), 'extra': sum(e['kind'] == 'extra' for e in E),
           'unique_examples': len(pids), 'unestablished': sum(1 for e in E if e.get('unestablished')),
           'grammar_notes': len(data['grammar']), 'sources': len(data['sources']), 'ru_lemmas': len(data.get('ru') or {})}
print('SUMMARY', json.dumps(summary, ensure_ascii=False))
cnt = [w for w in warnings if 'заявлено полных примеров' in w]
for w in [w for w in warnings if w not in cnt]: print('WARNING', w)
if cnt:
    print('WARNING', f'в {len(cnt)} вариантах число «Полных примеров для этого варианта» не совпадает со встроенными примерами; на сайте показано фактическое число: '
          + '; '.join(re.sub(r'^статья \d+ «(.+?)», вариант (.+?): заявлено полных примеров (\d+), встроено (\d+)$', r'«\1» \2 (\3→\4)', w) for w in cnt))
if problems: fail(problems)

# ---------- запись ----------

page = open(page_path, encoding='utf-8').read()
m = re.search(r'(<script type="application/json" id="data">)(.*?)(</script>)', page, re.S)
if not m: fail(['в странице нет блока данных'])
old = None
if m.group(2) != '__DATA__':
    try: old = json.loads(m.group(2).replace('<\\/', '</'))
    except Exception: old = None
old_built = old.pop('built', None) if isinstance(old, dict) else None
status = 'UNCHANGED' if old == json.loads(json.dumps(data)) else 'CHANGED'
moscow = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
data['built'] = old_built if status == 'UNCHANGED' and old_built else moscow.strftime('%d.%m.%Y')
new_json = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
page = page[:m.start(2)] + new_json + page[m.end(2):]
open(out, 'w', encoding='utf-8').write(page)
if site_dir:
    import sitegen
    sitegen.build_site(data, page, site_dir, base_url or '/')
    print('SITE', site_dir)
print('STATUS', status)
