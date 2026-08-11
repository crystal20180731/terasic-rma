'use strict';
/* Terasic RMA 查询 — 前端逻辑
 * 数据通过口令在浏览器内 AES-GCM 解密，口令不经过任何服务器。 */

let DATA = null;       // {updated,count,mismatchCount,records,meta}
let RECORDS = [];

/* ---------- 解密 ---------- */
async function decryptData(buf, password) {
  const bytes = new Uint8Array(buf);
  const salt = bytes.slice(0, 16);
  const nonce = bytes.slice(16, 28);
  const ct = bytes.slice(28);
  const enc = new TextEncoder();
  const keyMat = await crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: salt, iterations: 200000, hash: 'SHA-256' },
    keyMat, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: nonce }, key, ct);
  const text = new TextDecoder().decode(plain);
  return JSON.parse(text);
}

/* ---------- 工具 ---------- */
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));
}
function formatReport(s) {
  let t = esc(s);
  // 在章节点（一、二、…）前补换行保证分段，已有换行一并转 <br>
  t = t.replace(/([一二三四五六七八九十]、)/g, '\n$1');
  return t.replace(/\n/g, '<br>').replace(/^<br>/, '');
}
function warrantyClass(w) {
  if (w === '保内') return 'chip-green';
  if (w === '保外') return 'chip-red';
  return 'chip-gray';
}
function stateClass(s) {
  if (s === '已结案' || s === '结案') return 'chip-gray';
  return 'chip-amber';
}
function searchable(r) {
  return [r.rma, r.rmaNo, r.company, r.contact, r.product, r.series, r.sn, r.report,
    r.noteSales, r.noteTech, r.fault, r.sales, r.stateRaw].join(' ').toLowerCase();
}

/* ---------- 初始化 ---------- */
async function unlock() {
  const pw = document.getElementById('pwInput').value.trim();
  const err = document.getElementById('gateErr');
  if (!pw) { err.textContent = '请输入口令'; return; }
  if (!crypto.subtle) { err.textContent = '当前环境不支持解密，请用 http(s) 访问'; return; }
  err.textContent = '解密中…';
  try {
    const resp = await fetch('data.enc');
    if (!resp.ok) throw new Error('数据文件未找到');
    const buf = await resp.arrayBuffer();
    DATA = await decryptData(buf, pw);
    RECORDS = DATA.records;
    document.getElementById('gate').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
    document.getElementById('updatedAt').textContent = DATA.updated || '—';
    document.getElementById('totalCount').textContent = DATA.count;
    document.getElementById('mismatchBadge').textContent = DATA.mismatchCount;
    buildFilters();
    applyFilters();
    renderMismatch();
  } catch (e) {
    err.textContent = '✗ 口令错误或无权限访问';
  }
}

function lock() {
  document.getElementById('app').classList.add('hidden');
  document.getElementById('gate').classList.remove('hidden');
  document.getElementById('pwInput').value = '';
  document.getElementById('gateErr').textContent = '';
}

/* ---------- 筛选下拉 ---------- */
function fillSelect(id, values, allLabel) {
  const sel = document.getElementById(id);
  sel.innerHTML = '';
  const o0 = document.createElement('option');
  o0.value = ''; o0.textContent = allLabel;
  sel.appendChild(o0);
  values.forEach(v => {
    const o = document.createElement('option');
    o.value = v; o.textContent = v;
    sel.appendChild(o);
  });
}
function buildFilters() {
  const m = DATA.meta;
  const years = m.years || [];
  const yf = document.getElementById('fYearFrom');
  const yt = document.getElementById('fYearTo');
  yf.innerHTML = ''; yt.innerHTML = '';
  const oa = document.createElement('option'); oa.value = ''; oa.textContent = '全部';
  yf.appendChild(oa.cloneNode(true)); yt.appendChild(oa.cloneNode(true));
  years.forEach(y => {
    const o1 = document.createElement('option'); o1.value = y; o1.textContent = y; yf.appendChild(o1);
    const o2 = document.createElement('option'); o2.value = y; o2.textContent = y; yt.appendChild(o2);
  });
  if (years.length) { yt.value = years[years.length - 1]; }
  fillSelect('fCompany', m.companies, '全部单位');
  fillSelect('fProduct', m.products, '全部产品');
}

/* ---------- 查询 + 筛选 ---------- */
function isClosed(r) {
  return r.stateCat === '已结案' || r.closed === 'Y' || r.closed === '已结案';
}

function getFilters() {
  const yf = parseInt(document.getElementById('fYearFrom').value) || 0;
  const yt = parseInt(document.getElementById('fYearTo').value) || 9999;
  return {
    yf, yt,
    rma: document.getElementById('fRma').value.trim().toLowerCase(),
    contact: document.getElementById('fContact').value.trim().toLowerCase(),
    company: document.getElementById('fCompany').value,
    product: document.getElementById('fProduct').value,
    closed: document.getElementById('fClosed').value,
    sn: document.getElementById('fSn').value.trim().toLowerCase(),
    q: document.getElementById('searchBox').value.trim().toLowerCase(),
  };
}
function applyFilters() {
  const f = getFilters();
  let list = RECORDS.filter(r => {
    const y = parseInt(r.year) || 0;
    if (f.yf && y < f.yf) return false;
    if (f.yt && y > f.yt) return false;
    if (f.rma && !(r.rma.toLowerCase().includes(f.rma) || r.rmaNo.toLowerCase().includes(f.rma))) return false;
    if (f.contact && !r.contact.toLowerCase().includes(f.contact)) return false;
    if (f.company && r.company !== f.company) return false;
    if (f.product && r.product !== f.product) return false;
    if (f.closed === 'closed' && !isClosed(r)) return false;
    if (f.closed === 'open' && isClosed(r)) return false;
    if (f.sn && !r.sn.toLowerCase().includes(f.sn)) return false;
    if (f.q && !searchable(r).includes(f.q)) return false;
    return true;
  });
  const sort = document.getElementById('sortBy').value;
  list.sort((a, b) => {
    if (sort === 'company') return a.company.localeCompare(b.company, 'zh');
    const ta = a.reportTime, tb = b.reportTime;
    return sort === 'time-asc' ? ta.localeCompare(tb) : tb.localeCompare(ta);
  });
  renderCards(list);
}

/* ---------- 卡片渲染 ---------- */
function renderCards(list) {
  const box = document.getElementById('cards');
  const tip = document.getElementById('emptyTip');
  document.getElementById('resultCount').textContent = list.length + ' 条结果';
  box.innerHTML = '';
  if (!list.length) { tip.classList.remove('hidden'); return; }
  tip.classList.add('hidden');
  const frag = document.createDocumentFragment();
  list.forEach(r => {
    const el = document.createElement('div');
    el.className = 'card';
    const warn = r.checkFlag.startsWith('不符') ? `<span class="flag-warn">⚠ ${esc(r.checkFlag)}</span>` : '';
    el.innerHTML = `
      <div class="card-top">
        <span class="rma-no">${esc(r.rma)}</span>
        <span class="chip ${warrantyClass(r.warranty)}">${esc(r.warranty || '—')}</span>
      </div>
      <div class="card-co">${esc(r.company || '未知单位')}</div>
      <div class="card-meta">
        <span class="chip chip-blue">${esc(r.product || '—')}</span>
        ${r.fault ? `<span class="chip chip-gray">${esc(r.fault)}</span>` : ''}
        <br>联系人：${esc(r.contact || '—')} · 业务：${esc(r.sales || '—')}
        <br>报修：${esc(r.reportTime || '—')} · 状态：<span class="chip ${stateClass(r.stateCat)}">${esc(r.stateCat || '—')}</span>
        ${r.fee ? `<br>费用：${esc(r.fee)} ${esc(r.currency)}` : ''}
        ${warn ? `<br>${warn}` : ''}
      </div>`;
    el.onclick = () => openDetail(r);
    frag.appendChild(el);
  });
  box.appendChild(frag);
}

/* ---------- 详情弹窗 ---------- */
function openDetail(r) {
  const warn = r.checkFlag.startsWith('不符')
    ? `<span class="tag-warn">⚠ ${esc(r.checkFlag)}（表单标注 ${esc(r.warranty)} / 90天推算 ${esc(r.calcWarranty)}）</span>` : '';
  const body = `
    <div class="m-title">${esc(r.rma)}</div>
    <div class="m-sub">${esc(r.company || '')} · 报修时间 ${esc(r.reportTime || '—')} ${warn}</div>
    <div class="m-grid">
      <div><b>客户单位</b>${esc(r.company || '—')}</div>
      <div><b>联系人</b>${esc(r.contact || '—')}</div>
      <div><b>电话</b>${esc(r.phone || '—')}</div>
      <div><b>邮箱</b>${esc(r.email || '—')}</div>
      <div><b>产品</b>${esc(r.product || '—')}</div>
      <div><b>系列</b>${esc(r.series || '—')}</div>
      <div><b>序列号</b>${esc(r.sn || '—')}</div>
      <div><b>数量</b>${esc(r.qty || '—')}</div>
      <div><b>保固</b>${esc(r.warranty || '—')}</div>
      <div><b>维修费用</b>${esc(r.fee || '0')} ${esc(r.currency)}</div>
      <div><b>业务员</b>${esc(r.sales || '—')}</div>
      <div><b>维修人员</b>${esc(r.repairman || '—')}</div>
      <div><b>状态</b>${esc(r.stateCat || '—')}（${esc(r.stateRaw || '—')}）</div>
      <div><b>是否结案</b>${esc(r.closed || '—')}</div>
      <div><b>出货日期</b>${esc(r.shipDate || '—')}</div>
      <div><b>故障类型</b>${esc(r.fault || '—')}</div>
    </div>
    ${r.report ? `<div class="m-sec"><h4>维修报告全文</h4><div class="body">${formatReport(r.report)}</div></div>` : ''}
    ${r.noteSales ? `<div class="m-sec"><h4>销售备注</h4><div class="body">${esc(r.noteSales)}</div></div>` : ''}
    ${r.noteTech ? `<div class="m-sec"><h4>技术备注</h4><div class="body">${esc(r.noteTech)}</div></div>` : ''}
  `;
  document.getElementById('modalBody').innerHTML = body;
  document.getElementById('modal').classList.remove('hidden');
}
function closeModal() { document.getElementById('modal').classList.add('hidden'); }

/* ---------- 保固待核 ---------- */
function renderMismatch() {
  const list = RECORDS.filter(r => r.checkFlag.startsWith('不符'));
  document.getElementById('mMismatchCount').textContent = list.length;
  document.getElementById('mismatchBadge').textContent = list.length;
  const tb = document.getElementById('mMismatchBody');
  tb.innerHTML = '';
  list.forEach(r => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><a style="color:var(--brand);cursor:pointer" data-rma="${esc(r.rma)}">${esc(r.rma)}</a></td>
      <td>${esc(r.company)}</td>
      <td>${esc(r.product)}</td>
      <td class="t-${r.warranty === '保内' ? 'green' : 'red'}">${esc(r.warranty)}</td>
      <td>${esc(r.shipDate || '—')}</td>
      <td class="t-${r.calcWarranty === '保内' ? 'green' : 'red'}">${esc(r.calcWarranty)}</td>
      <td>${esc(r.reportTime)}</td>
      <td class="t-red">${esc(r.checkFlag)}</td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll('a[data-rma]').forEach(a => {
    a.onclick = () => {
      const rec = RECORDS.find(x => x.rma === a.dataset.rma);
      if (rec) { switchTab('query'); openDetail(rec); }
    };
  });
}

/* ---------- 客户档案 ---------- */
function renderCustomer(name) {
  const box = document.getElementById('custResult');
  if (!name) { box.innerHTML = '<p style="color:var(--muted)">输入客户单位名称后查看其全部历史工单、报修次数与故障分布。</p>'; return; }
  const list = RECORDS.filter(r => r.company && r.company.toLowerCase().includes(name.toLowerCase()));
  if (!list.length) { box.innerHTML = '<p style="color:var(--muted)">未找到匹配的客户单位。</p>'; return; }
  // 同公司可能有多条，取精确匹配优先
  const exact = list.filter(r => r.company.toLowerCase() === name.toLowerCase());
  const use = exact.length ? exact : list;
  const total = use.length;
  const closed = use.filter(r => r.closed === 'Y' || r.closed === '已结案').length;
  const inW = use.filter(r => r.warranty === '保内').length;
  const outW = use.filter(r => r.warranty === '保外').length;
  const feeSum = use.reduce((s, r) => s + (parseFloat(r.fee) || 0), 0);
  const faultCnt = {};
  use.forEach(r => { if (r.fault) faultCnt[r.fault] = (faultCnt[r.fault] || 0) + 1; });
  const faultTop = Object.entries(faultCnt).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const prods = {};
  use.forEach(r => { if (r.product) prods[r.product] = (prods[r.product] || 0) + 1; });
  const prodTop = Object.entries(prods).sort((a, b) => b[1] - a[1]).slice(0, 5);

  let rows = '';
  use.slice().sort((a, b) => b.reportTime.localeCompare(a.reportTime)).forEach(r => {
    rows += `<tr><td>${esc(r.rma)}</td><td>${esc(r.reportTime)}</td><td>${esc(r.product)}</td>
      <td><span class="chip ${warrantyClass(r.warranty)}">${esc(r.warranty || '—')}</span></td>
      <td>${esc(r.stateCat || '—')}</td><td>${esc(r.fault || '—')}</td>
      <td>${esc(r.fee || '0')} ${esc(r.currency)}</td></tr>`;
  });
  box.innerHTML = `
    <div class="cust-head">
      <h2>${esc(use[0].company)}</h2>
      <div style="color:var(--muted);font-size:13px">共匹配 ${total} 条工单（精确名称 ${exact.length} 条）</div>
      <div class="cust-stat">
        <div><b>${total}</b>总工单</div>
        <div><b>${closed}</b>已结案</div>
        <div><b style="color:var(--green)">${inW}</b>保内</div>
        <div><b style="color:var(--red)">${outW}</b>保外</div>
        <div><b>¥${feeSum.toFixed(0)}</b>累计费用</div>
      </div>
    </div>
    <div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px">
      <div style="flex:1;min-width:260px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px;box-shadow:var(--shadow)">
        <h4 style="margin:0 0 8px;color:var(--brand);font-size:13px">常见故障</h4>
        ${faultTop.map(f => `<div style="font-size:13px;padding:3px 0">${esc(f[0])} <b>×${f[1]}</b></div>`).join('') || '<div style="color:var(--muted)">—</div>'}
      </div>
      <div style="flex:1;min-width:260px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px;box-shadow:var(--shadow)">
        <h4 style="margin:0 0 8px;color:var(--brand);font-size:13px">涉及产品</h4>
        ${prodTop.map(p => `<div style="font-size:13px;padding:3px 0">${esc(p[0])} <b>×${p[1]}</b></div>`).join('') || '<div style="color:var(--muted)">—</div>'}
      </div>
    </div>
    <table class="mini-table"><thead><tr>
      <th>RMA 编号</th><th>报修时间</th><th>产品</th><th>保固</th><th>状态</th><th>故障</th><th>费用</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
}

/* ---------- Tab 切换 ---------- */
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.getElementById('tab-query').classList.toggle('hidden', name !== 'query');
  document.getElementById('tab-mismatch').classList.toggle('hidden', name !== 'mismatch');
  document.getElementById('tab-customer').classList.toggle('hidden', name !== 'customer');
}

/* ---------- 事件绑定 ---------- */
window.addEventListener('DOMContentLoaded', () => {
  document.getElementById('unlockBtn').onclick = unlock;
  document.getElementById('pwInput').addEventListener('keydown', e => { if (e.key === 'Enter') unlock(); });
  document.getElementById('lockBtn').onclick = lock;
  document.getElementById('modalClose').onclick = closeModal;
  document.getElementById('modal').onclick = e => { if (e.target.id === 'modal') closeModal(); };
  document.querySelectorAll('.tab').forEach(t => t.onclick = () => switchTab(t.dataset.tab));
  ['searchBox', 'fRma', 'fContact', 'fSn', 'fYearFrom', 'fYearTo', 'fCompany', 'fProduct', 'fClosed'].forEach(id => {
    document.getElementById(id).addEventListener('input', applyFilters);
  });
  document.getElementById('fYearFrom').addEventListener('change', applyFilters);
  document.getElementById('fYearTo').addEventListener('change', applyFilters);
  document.getElementById('fCompany').addEventListener('change', applyFilters);
  document.getElementById('fProduct').addEventListener('change', applyFilters);
  document.getElementById('fClosed').addEventListener('change', applyFilters);
  document.getElementById('sortBy').addEventListener('change', applyFilters);
  document.getElementById('searchClear').onclick = () => { document.getElementById('searchBox').value = ''; applyFilters(); };
  document.getElementById('resetBtn').onclick = () => {
    ['fRma', 'fContact', 'fSn', 'searchBox'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('fYearFrom').value = '';
    document.getElementById('fYearTo').value = (DATA.meta.years || []).slice(-1)[0] || '';
    document.getElementById('fCompany').value = '';
    document.getElementById('fProduct').value = '';
    document.getElementById('fClosed').value = '';
    applyFilters();
  };
  let ct;
  document.getElementById('custSearch').addEventListener('input', e => {
    clearTimeout(ct); ct = setTimeout(() => renderCustomer(e.target.value.trim()), 200);
  });
});
