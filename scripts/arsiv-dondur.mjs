#!/usr/bin/env node
// Canlı HANDOFF.md / PLAN.md dosyalarını küçük tutar: fazla blok ve maddeleri docs/archive/ altına
// BİREBİR taşır (silmez). CONVENTIONS §1.2 ve §3 bu betiği çağırır.
//
//   node scripts/arsiv-dondur.mjs            # ne taşınacağını söyler, yazmaz
//   node scripts/arsiv-dondur.mjs --apply    # taşır
//
// Kurallar (canlı dosyada kalan):
//   HANDOFF.md  son 5 farklı görev kimliğinin blokları + açık (pending/in-progress/blocked/review) görevlerin blokları
//   PLAN.md K   her #### K<kod> bloğunda son 3 madde + açık görevlere ait maddeler
//   PLAN.md C/D her bölümde son 5 madde + açık görevlere ait maddeler
// Gereksinim tablolarına, `## K.` ve `#### K<kod>` başlıklarına dokunulmaz.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OPEN = new Set(['pending', 'in-progress', 'blocked', 'review']);
const K_POINTER = /^_Önceki maddeler:/;
const CD_POINTER = /^_Eski maddeler:/;

/** Metindeki `tm 175`, `tm 175, 176`, `tm 175–177` ifadelerinden görev kimlikleri. */
export function tmIds(text) {
  const ids = new Set();
  for (const m of text.matchAll(/\btm\s+(\d+(?:\s*(?:[,–-]|ve)\s*\d+)*)/g)) {
    const parts = m[1].split(/\s*(,|–|-|ve)\s*/).filter((x) => x !== '');
    for (let i = 0; i < parts.length; i += 2) {
      const a = Number(parts[i]);
      if (parts[i + 1] === '–' || parts[i + 1] === '-') {
        const b = Number(parts[i + 2]);
        for (let n = a; n <= b; n++) ids.add(String(n));
      } else ids.add(String(a));
    }
  }
  return ids;
}

const touches = (text, keep) => [...tmIds(text)].some((id) => keep.has(id));

// ---------------------------------------------------------------- HANDOFF
export function rotateHandoff(text, keepIds) {
  const lines = text.split('\n');
  const start = lines.findIndex((l) => l.startsWith('## Task log (newest-first)'));
  if (start < 0) throw new Error('HANDOFF: "## Task log (newest-first)" başlığı yok');
  const head = lines.slice(0, start + 1);
  const blocks = [];
  for (let i = start + 1; i < lines.length; i++) {
    if (lines[i].startsWith('## ')) blocks.push([]);
    if (!blocks.length) head.push(lines[i]);
    else blocks[blocks.length - 1].push(lines[i]);
  }
  const idsOf = (b) => {
    const m = b[0].match(/^## (\d+(?:\s*,\s*\d+)*)\s+—/);
    return m ? m[1].split(/\s*,\s*/) : [];
  };
  const keep = [];
  const moved = [];
  for (const b of blocks) (idsOf(b).some((id) => keepIds.has(id)) ? keep : moved).push(b);
  return { head, keep, moved, idsOf };
}

/** Üstten ilk 5 farklı görev kimliği + açık görevler. */
export function handoffKeepIds(text, tasks) {
  const { keep, moved, idsOf } = rotateHandoff(text, new Set());
  const ids = new Set();
  for (const b of [...keep, ...moved]) {
    for (const id of idsOf(b)) if (ids.size < 5) ids.add(id);
    if (ids.size >= 5) break;
  }
  for (const t of tasks) if (OPEN.has(t.status)) ids.add(String(t.id));
  return ids;
}

// ---------------------------------------------------------------- bölüm/madde ayrıştırma
/** `- ` ile başlayan maddeler; sonraki girintili/boş satırlar maddenin parçasıdır. */
function splitEntries(lines, isPointer) {
  const intro = [];
  const entries = [];
  let fence = false;
  for (const l of lines) {
    if (/^```/.test(l)) fence = !fence;
    if (!fence && /^- /.test(l)) entries.push([l]);
    else if (isPointer && isPointer.test(l)) continue;
    else if (entries.length) entries[entries.length - 1].push(l);
    else intro.push(l);
  }
  return { intro, entries };
}

function pick(entries, { keepIds, lastN }) {
  const keep = [];
  const moved = [];
  entries.forEach((e, i) => {
    const text = e.join('\n');
    (i >= entries.length - lastN || touches(text, keepIds) ? keep : moved).push(e);
  });
  return { keep, moved };
}

/** Bir `## ` bölümünün [başlangıç, bitiş) satır aralığı. */
function sectionRange(lines, re) {
  const s = lines.findIndex((l) => re.test(l));
  if (s < 0) throw new Error(`bölüm yok: ${re}`);
  let e = lines.length;
  for (let i = s + 1; i < lines.length; i++) if (/^## /.test(lines[i])) { e = i; break; }
  return [s, e];
}

// ---------------------------------------------------------------- PLAN K blokları
export function rotateK(plan, opts) {
  const lines = plan.split('\n');
  const [s, e] = sectionRange(lines, /^## K\. /);
  const out = lines.slice(0, s + 1);
  const archive = [];
  let fence = false;
  let i = s + 1;
  // giriş (örnek bloğu çitin içinde)
  for (; i < e; i++) {
    if (/^```/.test(lines[i])) fence = !fence;
    if (!fence && /^#### /.test(lines[i])) break;
    out.push(lines[i]);
  }
  let count = 0;
  while (i < e) {
    let j = i + 1;
    while (j < e && !/^#### /.test(lines[j])) j++;
    const heading = lines[i];
    const code = heading.match(/^#### (K[\w.\-]+)/)?.[1];
    // sondaki boş satırlar bloğa değil ayırıcıya aittir
    let end = j;
    while (end > i + 1 && lines[end - 1] === '') end--;
    const { intro, entries } = splitEntries(lines.slice(i + 1, end), K_POINTER);
    const { keep, moved } = pick(entries, opts);
    out.push(heading, ...intro, ...keep.flat());
    if (moved.length) {
      out.push(`_Önceki maddeler: docs/archive/plan-kanit/ (#### ${code})_`);
      archive.push(heading, ...moved.flat(), '');
      count += moved.length;
    } else if (lines.slice(i + 1, end).some((l) => K_POINTER.test(l))) {
      out.push(`_Önceki maddeler: docs/archive/plan-kanit/ (#### ${code})_`);
    }
    out.push(...lines.slice(end, j));
    i = j;
  }
  out.push(...lines.slice(e));
  return { text: out.join('\n'), archive, count };
}

// ---------------------------------------------------------------- PLAN C/D bölümleri
export function rotateSection(plan, re, opts) {
  const lines = plan.split('\n');
  const [s, e] = sectionRange(lines, re);
  const { intro, entries } = splitEntries(lines.slice(s + 1, e), CD_POINTER);
  const { keep, moved } = pick(entries, opts);
  const out = [...lines.slice(0, s + 1), ...intro];
  const firstId = moved.length ? moved[0][0].match(/^- \*\*([CD])\d+/)?.[1] : null;
  if (moved.length || lines.slice(s + 1, e).some((l) => CD_POINTER.test(l))) {
    // girişin sonundaki boş satırı koru, işaretçiyi maddelerden hemen önce yaz
    while (out.length && out[out.length - 1] === '') out.pop();
    out.push('', `_Eski maddeler: docs/archive/plan-kanit/ — ara: grep -rn '^- \\*\\*${firstId ?? '[CD]'}<no>' docs/archive/plan-kanit_`, '');
  }
  out.push(...keep.flat(), ...lines.slice(e));
  return { text: out.join('\n'), archive: [lines[s], '', ...moved.flat()], count: moved.length };
}

// ---------------------------------------------------------------- CLI
function main() {
  const apply = process.argv.includes('--apply');
  const date = new Date().toISOString().slice(0, 10);
  const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
  const tasks = JSON.parse(read('.taskmaster/tasks/tasks.json')).master.tasks;
  const open = new Set(tasks.filter((t) => OPEN.has(t.status)).map((t) => String(t.id)));

  const handoff = read('HANDOFF.md');
  const hk = rotateHandoff(handoff, handoffKeepIds(handoff, tasks));
  const plan0 = read('PLAN.md');
  const k = rotateK(plan0, { keepIds: open, lastN: 3 });
  const c = rotateSection(k.text, /^## C\. /, { keepIds: open, lastN: 5 });
  const d = rotateSection(c.text, /^## D\. /, { keepIds: open, lastN: 5 });
  console.log(`HANDOFF: ${hk.moved.length} blok taşınacak · PLAN K: ${k.count} madde · C: ${c.count} · D: ${d.count}`);
  if (!apply) return;

  const write = (p, t) => {
    fs.mkdirSync(path.dirname(path.join(ROOT, p)), { recursive: true });
    fs.writeFileSync(path.join(ROOT, p), t);
  };
  if (hk.moved.length) {
    const f = `docs/archive/handoff/HANDOFF-arsiv-${date}.md`;
    const MARK = '<!-- bloklar (newest-first) -->';
    const blocks = hk.moved.flat().join('\n');
    const old = fs.existsSync(path.join(ROOT, f)) ? read(f) : null;
    write(f, old
      ? old.replace(MARK, `${MARK}\n\n${blocks.replace(/\n+$/, '')}\n`)
      : `# HANDOFF arşivi — ${date}\n\nKaynak: HANDOFF.md (canlı dosyadan taşındı, birebir). Blok sayısı: ${hk.moved.length}.\n\n${MARK}\n\n${blocks}`);
    write('HANDOFF.md', [...hk.head, ...hk.keep.flat()].join('\n').replace(/\n*$/, '\n'));
  }
  const arch = [...(k.archive.length ? ['## K. Kanıt Geçmişi (arşiv)', '', ...k.archive] : [])];
  const cd = [c, d].filter((x) => x.count).flatMap((x) => [...x.archive, '']);
  if (arch.length || cd.length) {
    const f = `docs/archive/plan-kanit/PLAN-kanit-arsiv-${date}.md`;
    const body = [...arch, ...cd].join('\n');
    const old = fs.existsSync(path.join(ROOT, f)) ? read(f) + '\n' : `# PLAN arşivi — ${date}\n\nKaynak: PLAN.md (K blokları, C ve D bölümleri; canlı dosyadan taşındı, birebir).\n\n`;
    write(f, old + body + '\n');
    write('PLAN.md', d.text);
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) main();
