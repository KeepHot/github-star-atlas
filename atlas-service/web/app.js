(function () {
'use strict';
const categories={learn:'学习与教程',lists:'资源与清单',agent:'智能体',ai:'人工智能',web:'Web 与前端',backend:'后端与服务',dev:'开发者工具',ops:'运维与云',apps:'应用与效率',media:'媒体与创意',security:'安全与隐私',data:'数据与分析'};
const titles={top:'累计 Star · Top 2000',daily:'每日趋势',weekly:'每周趋势',monthly:'每月趋势'};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function safeURL(v){try{const u=new URL(v);return u.protocol==='https:'&&u.hostname==='github.com'?u.href:'#';}catch{return '#';}}
function dataset(data,view){return view==='top'?(Array.isArray(data?.repositories)?data.repositories:[]):(Array.isArray(data?.trending?.[view]?.repositories)?data.trending[view].repositories:[]);}
function selectRows(rows,{query='',category='',language='',sort='rank'}={}){const q=query.trim().toLocaleLowerCase('zh-CN');return rows.filter(r=>(!category||r.category===category)&&(!language||r.language===language)&&(!q||[r.name,r.summary,r.original,r.language].some(x=>String(x??'').toLocaleLowerCase('zh-CN').includes(q)))).slice().sort((a,b)=>sort==='stars'?Number(b.stars||0)-Number(a.stars||0)||a.rank-b.rank:sort==='name'?String(a.name).localeCompare(String(b.name)):Number(a.rank)-Number(b.rank));}
function paginate(rows,page=1,size=36){const pages=Math.max(1,Math.ceil(rows.length/size));const current=Math.min(pages,Math.max(1,Number(page)||1));return {rows:rows.slice((current-1)*size,current*size),page:current,pages};}
function csv(rows,view){const cell=v=>'"'+String(v??'').replace(/^[=+@-]/,"'$&").replace(/"/g,'""')+'"';return '\ufeff'+[['榜单','官方排名','项目','累计Star','周期新增Star','语言','分类','简介来源','简介','链接'],...rows.map(r=>[titles[view],r.rank,r.name,r.stars,view==='top'?'':r.periodStars,r.language,categories[r.category]||r.category,r.summarySource,r.summary,r.url])].map(r=>r.map(cell).join(',')).join('\r\n');}
function freshness(updatedAt,status,now=Date.now()){if(!updatedAt||!Number.isFinite(Date.parse(updatedAt)))return 'missing';if(status==='error')return 'error';if(status==='stale'||now-Date.parse(updatedAt)>6*3600000)return 'stale';return 'ok';}
globalThis.AtlasFunctions={esc,safeURL,dataset,selectRows,paginate,csv,freshness};
if(typeof document==='undefined')return;
const $=id=>document.getElementById(id),data=globalThis.ATLAS_DATA||{},params=new URLSearchParams(location.hash.slice(1));
const state={view:titles[params.get('view')]?params.get('view'):'top',layout:params.get('layout')==='rank'?'rank':'content',query:params.get('q')||'',category:categories[params.get('category')]?params.get('category'):'',language:params.get('language')||'',sort:['rank','stars','name'].includes(params.get('sort'))?params.get('sort'):'rank',page:Number(params.get('page'))||1};
const num=n=>Number.isFinite(Number(n))?Number(n).toLocaleString('zh-CN'):'—';
const date=v=>v&&Number.isFinite(Date.parse(v))?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(v)):'未知';
let visible=[];
function save(){const p=new URLSearchParams({view:state.view,layout:state.layout,q:state.query,category:state.category,language:state.language,sort:state.sort,page:state.page});try{history.replaceState(null,'','#'+p);}catch{}}
function render(){
const trend=data.trending?.[state.view],rows=dataset(data,state.view),isTop=state.view==='top',updated=isTop?data.topUpdatedAt:trend?.updatedAt;
const filtered=selectRows(rows,state),paging=paginate(filtered,state.page);state.page=paging.page;visible=filtered;
$('search').value=state.query;$('clear').hidden=!state.query;
$('categories').innerHTML=[['','全部用途'],...Object.entries(categories)].map(([id,label])=>`<button class="cat ${state.category===id?'active':''}" data-category="${id}" aria-pressed="${state.category===id}"><span class="dot"></span><span>${label}</span><em>${rows.filter(r=>!id||r.category===id).length}</em></button>`).join('');
const langs=[...new Set(rows.map(r=>r.language).filter(Boolean))].sort();$('language').innerHTML='<option value="">全部语言</option>'+langs.map(l=>`<option value="${esc(l)}">${esc(l)}</option>`).join('');if(state.language&&!langs.includes(state.language)){state.language='';return render();}$('language').value=state.language;
$('sort').innerHTML=`<option value="rank">${isTop?'累计 Star 排名':'官方趋势顺序'}</option><option value="stars">累计 Star 从高到低</option><option value="name">项目名称</option>`;$('sort').value=state.sort;
$('total').textContent=num(rows.length);$('languages').textContent=num(langs.length);$('stars').textContent=rows.length?num(Math.max(...rows.map(r=>Number(r.stars)||0))):'—';$('date').textContent=date(updated);$('scope').textContent=isTop?'公开非 fork · 包含归档':'官方 Trending · 独立榜单';
$('breadcrumb').textContent=titles[state.view];$('results-title').textContent=titles[state.view];document.title=titles[state.view]+' · GitHub 开源星图';
const fresh=freshness(updated,isTop?(data.status?.state==='error'?'error':undefined):trend?.status);
$('status').className='status'+(fresh==='ok'?'':' warning');
$('status').textContent=!rows.length?(fresh==='missing'?'暂无此榜单快照。请在采集完成后重新载入。':'此榜单暂无项目；请检查来源或稍后重新载入。'):fresh==='error'?'本次采集失败，正在显示上次可用快照。':fresh==='stale'?'快照已超过 6 小时或来源采集失败；当前保留上次可用结果。':fresh==='missing'?'采集时间未知，请核对来源后使用。':data.status?.state==='partial'?'部分来源更新失败；当前榜单的采集时间见下方。':'已载入采集快照，可离线浏览。';
const source=isTop?(data.source||'https://api.github.com/search/repositories'):(trend?.source||`https://github.com/trending?since=${state.view}`);
const sourceSafe=/^https:\/\/(api\.)?github\.com\//.test(source)?source:'#';$('source').innerHTML=`来源：<a href="${esc(sourceSafe)}" target="_blank" rel="noopener noreferrer">${isTop?'GitHub 搜索 API':'GitHub Trending · '+titles[state.view]}</a> · 采集于 ${esc(date(updated))}（北京时间）${isTop?' · 按累计 Star':' · 周期新增来自官方页面，范围独立于 Top 2000'}`;
$('count').textContent=`筛选 ${num(filtered.length)} / ${num(rows.length)} 项 · 每页 36 项`;
$('results').className=state.layout==='rank'?'ranking':'grid';
$('results').innerHTML=paging.rows.length?paging.rows.map(r=>`<article class="project"><div class="cardtop"><span class="rank mono">#${esc(r.rank)}</span><span class="stars"><i aria-hidden="true">★</i>${num(r.stars)}</span></div><div class="identity"><div class="owner mono">${esc(String(r.name).split('/')[0])}</div><h3><a href="${esc(safeURL(r.url))}" target="_blank" rel="noopener noreferrer">${esc(String(r.name).split('/').slice(1).join('/')||r.name)}</a></h3></div><div class="summary"><p>${esc(r.summary||r.original||'暂无项目描述')}</p><span class="source-badge">${r.summarySource==='editorial'?'中文编辑简介':'官方原始描述'}</span>${r.original&&r.summarySource==='editorial'?`<details><summary>查看官方原始描述</summary><p>${esc(r.original)}</p></details>`:''}</div><div class="cardfoot"><span class="lang">${esc(r.language||'未标注语言')}</span><span class="badge">${esc(categories[r.category]||'未分类')}</span>${r.archived?'<span class="badge archived">已归档</span>':''}${!isTop?`<span>周期新增 ${r.periodStars==null?'未知':'+'+num(r.periodStars)+' ★'}</span>`:`<span>日 / 周 / 月增长：${['daily','weekly','monthly'].map(k=>r.growth?.[k]==null?'未知':num(r.growth[k])).join(' / ')}</span>`}</div></article>`).join(''):`<div class="empty"><h2>${rows.length?'没有匹配的项目':'暂无可用榜单'}</h2><p>${rows.length?'试试更短的关键词，或重置全部筛选。':'稍后重新载入，或切换其他榜单。'}</p><button data-action="reset">重置全部筛选</button></div>`;
$('previous').disabled=state.page<=1;$('next').disabled=state.page>=paging.pages;$('page').textContent=`第 ${state.page} / ${paging.pages} 页`;$('export').disabled=!visible.length;$('export').textContent=`导出筛选结果 CSV (${filtered.length})`;
document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===state.view)));document.querySelectorAll('[data-layout]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.layout===state.layout)));save();
}
function reset(){Object.assign(state,{query:'',category:'',language:'',sort:'rank',page:1});render();$('search').focus();}
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.view){state.view=b.dataset.view;state.sort='rank';state.page=1;state.language='';render();}else if(b.dataset.layout){state.layout=b.dataset.layout;render();}else if('category'in b.dataset){state.category=b.dataset.category;state.page=1;render();}else if(b.dataset.action==='reset')reset();});
let composing=false;$('search').addEventListener('compositionstart',()=>composing=true);$('search').addEventListener('compositionend',()=>{composing=false;state.query=$('search').value;state.page=1;render();});$('search').addEventListener('input',()=>{if(!composing){state.query=$('search').value;state.page=1;render();}});
$('clear').onclick=()=>{state.query='';state.page=1;render();$('search').focus();};$('reset').onclick=reset;
for(const key of ['language','sort'])$(key).onchange=()=>{state[key]=$(key).value;state.page=1;render();};
for(const [id,step]of [['previous',-1],['next',1]])$(id).onclick=()=>{state.page+=step;render();$('results-title').focus();};
$('export').onclick=()=>{const blob=new Blob([csv(visible,state.view)],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`github-atlas-${state.view}-filtered-${visible.length}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('notice').textContent=`已导出${titles[state.view]}的全部筛选结果，共 ${visible.length} 项（包含所有分页）。`;};
render();
})();
