#!/usr/bin/env node
// Arşivleme sonrası doğrulama: canlı + arşiv, git'teki (HEAD) eski dosyayı satır satır kapsıyor mu?
//   node scripts/arsiv-dogrula.mjs [git-ref=HEAD]
// Kaybolan her satır listelenir; exit 1. Ayrıca: K bloğu sayısı, tablo satırları, tasks.json eşdeğerliği,
// panelin "suspicious-done" ölçütünün (kanıt bloğunda kapanışsız "Kalan") yeni bulgu doğurmaması.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ref = process.argv[2] ?? 'HEAD';
const git = (p) => execFileSync('git', ['show', `${ref}:${p}`], { cwd: ROOT, maxBuffer: 1 << 28 }).toString('utf8');
const rd = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const ls = (dir) => (fs.existsSync(path.join(ROOT, dir)) ? fs.readdirSync(path.join(ROOT, dir)).map((f) => path.join(dir, f)) : []);
const tally = (text) => {
  const m = new Map();
  for (const l of text.split('\n')) if (l.trim()) m.set(l, (m.get(l) ?? 0) + 1);
  return m;
};
let bad = 0;
const fail = (msg) => { bad++; console.log('✗', msg); };

function covered(name, oldText, parts) {
  const have = tally(parts.join('\n'));
  let lost = 0;
  for (const [l, n] of tally(oldText)) if ((have.get(l) ?? 0) < n) { lost += n - (have.get(l) ?? 0); if (lost <= 5) console.log('   kayıp:', l.slice(0, 120)); }
  lost ? fail(`${name}: ${lost} satır kayıp`) : console.log(`✓ ${name}: eski dosyanın tüm satırları canlı+arşivde`);
}

const handoffArch = ls('docs/archive/handoff').map(rd);
const planArch = ls('docs/archive/plan-kanit').map(rd);
covered('HANDOFF.md', git('HANDOFF.md'), [rd('HANDOFF.md'), ...handoffArch]);
covered('PLAN.md', git('PLAN.md'), [rd('PLAN.md'), ...planArch]);

// K bloğu sayısı ve gereksinim tabloları
const kCount = (t) => (t.match(/^#### K/gm) ?? []).length;
const oldPlan = git('PLAN.md');
const newPlan = rd('PLAN.md');
kCount(oldPlan) === kCount(newPlan) ? console.log(`✓ #### K blok sayısı aynı (${kCount(newPlan)})`) : fail(`K blok sayısı ${kCount(oldPlan)} → ${kCount(newPlan)}`);
const heads = (t) => t.split('\n').filter((l) => /^#{1,4} /.test(l) && !/^#### K99/.test(l)).join('\n');
heads(oldPlan) === heads(newPlan) ? console.log('✓ PLAN başlıkları aynı sırada') : fail('PLAN başlıkları değişti');
const tableLines = (t) => t.split('\n').filter((l) => l.startsWith('|')).join('\n');
tableLines(oldPlan) === tableLines(newPlan) ? console.log('✓ PLAN tablo satırları birebir aynı') : fail('PLAN tablo satırları değişti');

// panelin suspicious-done ölçütü (lib/diagnostics.mjs C3, kanıt bloğu kolu)
const SUSPECT = /(\*\*Kalan\b|henüz yapılmadı|henuz yapilmadi)/gi;
const RESOLVED = /(KAPANDI|kapand[ıi]|hak edilmiş|hak edilmis)/i;
function openBlocks(text) {
  const out = new Set();
  const i0 = text.indexOf('\n## K. ');
  const parts = text.slice(i0).split(/\n(?=#### )/);
  for (const p of parts) {
    const code = p.match(/^#### (K[\w.\-]+)/)?.[1];
    if (!code) continue;
    const hits = [...p.matchAll(SUSPECT)];
    if (hits.length && !RESOLVED.test(p.slice(hits.at(-1).index + hits.at(-1)[0].length))) out.add(code);
  }
  return out;
}
const before = openBlocks(oldPlan);
const after = openBlocks(newPlan);
const fresh = [...after].filter((c) => !before.has(c));
fresh.length ? fail(`yeni "şüpheli done" adayı K blokları: ${fresh.join(', ')}`) : console.log(`✓ suspicious-done: yeni aday yok (önce ${before.size}, sonra ${after.size})`);

// tasks.json
const tj = '.taskmaster/tasks/tasks.json';
const A = JSON.parse(git(tj)).master.tasks;
const B = JSON.parse(rd(tj)).master.tasks;
const strip = (t) => ({ id: t.id, title: t.title, status: t.status, dependencies: t.dependencies, priority: t.priority, description: t.description, updatedAt: t.updatedAt, subs: (t.subtasks ?? []).map((s) => [s.id, s.status, s.dependencies]) });
const dist = (a) => a.reduce((m, t) => ((m[t.status] = (m[t.status] ?? 0) + 1), m), {});
JSON.stringify(A.map(strip)) === JSON.stringify(B.map(strip)) && JSON.stringify(dist(A)) === JSON.stringify(dist(B))
  ? console.log(`✓ tasks.json: ${B.length} görev, durum ${JSON.stringify(dist(B))}, kimlik/başlık/bağımlılık/öncelik/alt görev aynı`)
  : fail('tasks.json meta alanları değişti');
const extra = A.length === B.length && A.every((t, i) => Object.keys(t).join() === Object.keys(B[i]).join());
extra ? console.log('✓ tasks.json alan kümeleri aynı') : fail('tasks.json alanları değişti');
// kısaltılan metnin tam hâli arşivde mi
const archTasks = ls('docs/archive/tasks').filter((f) => f.endsWith('.json')).map((f) => JSON.parse(rd(f)).master.tasks);
let miss = 0;
A.forEach((t, i) => {
  for (const k of ['details', 'testStrategy']) if (B[i][k] !== t[k] && !archTasks.some((a) => a[i]?.[k] === t[k])) miss++;
});
miss ? fail(`${miss} kısaltılmış alanın tam metni arşiv JSON'unda yok`) : console.log('✓ kısaltılan her details/testStrategy arşiv JSON\'unda birebir var');
process.exit(bad ? 1 : 0);
