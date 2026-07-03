let chart;
const fmt = (v, digits=2) => v === null || v === undefined ? '--' : Number(v).toFixed(digits);
const money = v => v === null || v === undefined ? '--' : Number(v).toFixed(4);
function cls(p){ if(p === null || p === undefined) return ''; if(p < 0) return 'discount'; if(p >= 5) return 'hot'; if(p >= 2) return 'warn'; return 'normal'; }
function statusText(p){ if(p === null || p === undefined) return '等待数据'; if(p < 0) return '折价'; if(p >= 5) return '高溢价'; if(p >= 2) return '偏高'; return '正常'; }
function renderCards(products){
  const el = document.getElementById('cards');
  el.innerHTML = products.map(p => `
    <article class="card">
      <div class="top">
        <div><div class="code">${p.code}</div><div class="name">${p.name}</div></div>
        <div class="badge">${statusText(p.premium)}</div>
      </div>
      <div class="premium ${cls(p.premium)}">${p.premium == null ? '--' : (p.premium >= 0 ? '+' : '') + fmt(p.premium,2) + '%'}</div>
      <div class="grid">
        <div class="metric"><div class="label">Market Price</div><div class="value">${money(p.price)}</div><div class="time">${p.price_time || '时间 --'}</div></div>
        <div class="metric"><div class="label">iNAV / NAV</div><div class="value">${money(p.inav)}</div><div class="time">${p.inav_time || '时间 --'}</div></div>
      </div>
      <div class="note">${p.status === 'error' ? '抓取失败：' + (p.error || '') : '来源：CSOP 官网'}</div>
    </article>`).join('');
}
function renderChart(products){
  const labels = [];
  const datasets = products.map(p => {
    const h = p.history || [];
    h.forEach(x => { if(!labels.includes(x.ts)) labels.push(x.ts); });
    const map = new Map(h.map(x => [x.ts, x.premium]));
    return { label: p.code, data: labels.map(t => map.get(t) ?? null), tension: .25, spanGaps: true };
  });
  const ctx = document.getElementById('premiumChart');
  if(chart) chart.destroy();
  chart = new Chart(ctx, { type:'line', data:{labels, datasets}, options:{responsive:true, plugins:{legend:{labels:{color:'#eef4ff'}}}, scales:{x:{ticks:{color:'#93a4b8', maxTicksLimit:6}, grid:{color:'rgba(147,164,184,.12)'}}, y:{ticks:{color:'#93a4b8', callback:v=>v+'%'}, grid:{color:'rgba(147,164,184,.12)'}}} } });
}
async function load(){
  document.getElementById('refreshBtn').disabled = true;
  try{
    const res = await fetch('/api/snapshot?ts=' + Date.now());
    const data = await res.json();
    renderCards(data.products || []);
    renderChart(data.products || []);
    document.getElementById('lastUpdated').textContent = '最后刷新 ' + new Date().toLocaleTimeString();
  }catch(e){
    document.getElementById('cards').innerHTML = `<div class="card">加载失败：${e}</div>`;
  }finally{
    document.getElementById('refreshBtn').disabled = false;
  }
}
document.getElementById('refreshBtn').addEventListener('click', load);
load();
setInterval(load, 60000);
