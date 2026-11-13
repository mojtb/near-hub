/* NEAR Hub Studio: the admin view, where a question is built from a query, a chart and its words.
   A prototype, and a project of its own. Nothing on the site links to it, and the site is complete without this folder.

   site/index.html fetches studio.css and then this file the first time #studio is opened. This file runs after the
   page's own script, so it reads the page's questions, charts and helpers by name, and it adds its two pages to the
   page's views at the end: V.studio (#studio) and V.studioEdit (#studio-edit). The preview is drawn by the same code
   as the page. In this prototype the warehouse is simulated: a query returns the rows the site already holds for the
   table it reads. */
/* Column names from the select list: split at top-level commas, then take the alias, or the bare column, or the expression itself */
const sxCols=sql=>{const m=/select\s+([\s\S]+?)\s+from\s/i.exec(sql||'');if(!m)return null;const parts=[];let depth=0,cur='';for(const ch of m[1]){if(ch==='(')depth++;if(ch===')')depth--;if(ch===','&&!depth){parts.push(cur);cur=''}else cur+=ch}parts.push(cur);return parts.map(p=>{p=p.trim().replace(/\s+/g,' ');const al=/(?:\)|\w)\s+(?:as\s+)?(\w+)$/i.exec(p);return al&&/[\s)]/.test(p)?al[1]:p.replace(/^.*\./,'')})};
/* The rows behind one chart of a question: the rows its exact query returns, or its time chart's own spec */
function sxChartResult(a,c,i){
  if(c.exact){const o=c.exact();return o.spec?{kind:'time',cols:o.cols,rows:o.spec.x.map((d,k)=>[d,...o.spec.series.map(z=>z.values[k])]),spec:o.spec,asOf:c.asOf}:{kind:'cat',cols:o.cols,rows:o.rows,asOf:c.asOf}}
  const sp=c.view&&c.view.spec?c.view.spec():typeof c.spec==='function'?c.spec():i===0&&typeof a.spec==='function'?a.spec():null;
  if(sp&&sp.x&&sp.series&&sp.series.length){const named=sxCols(c.sql||a.sql);return{kind:'time',cols:named&&named.length===sp.series.length+1?named:['date',...sp.series.map(z=>z.name)],rows:sp.x.map((d,k)=>[d,...sp.series.map(z=>z.values[k])]),spec:sp}}
  return null;
}
const sxRaw=v=>v==null?'<span class="sx-null">null</span>':typeof v==='number'?d3.format(',.4~f')(v):sxEsc(v);
const sxTable=(r,n)=>`<div class="sx-tw"><table class="t sx-t"><thead><tr>${r.cols.map((c,i)=>`<th class="${r.rows.some(x=>typeof x[i]==='number')?'num':''}">${sxEsc(c)}</th>`).join('')}</tr></thead><tbody>${r.rows.slice(0,n).map(x=>`<tr>${x.map(v=>`<td class="${typeof v==='number'?'num':''}">${sxRaw(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
const sxFmt=(c,v)=>v==null?'':typeof v!=='number'?String(v):/usd|price|mcap|tvl|fees|revenue|volume/i.test(c)?fmt.usd(v):/share|turnout|rate|pct/i.test(c)&&Math.abs(v)<=1.5?fmt.pct(v,Math.abs(v)<.1?1:0):Number.isInteger(v)?fmt.int(v):fmt.compact(v);
const SX_GROUPS=[
 ['Over time',['Bars','Line chart','Area chart','Step lines','Stacked bars','Waterfall','Diverging bars','Bars with targets','Calendar stripes','Bubble scatter','Rank over time']],
 ['Across labels',['Ranked bars','Treemap','Flow diagram','Stacked columns','Rank matrix','Bubble chart','Table']],
 ['Built for one question',['Interactive model','Compare tool','Dot strip','Commands']]];
const SX_FORMS=SX_GROUPS.flatMap(g=>g[1]);
const SX_TIME={'Bars':'bar','Line chart':'line','Area chart':'area','Stacked bars':'stack','Step lines':'line'};
const SX_PAL=['#3f6fe8','#00a874','#d97f2e','#7f62e0','#0f9a8a','#c9932a','#d9658f','#5f7a8a'];
/* What a result offers: a date and series, or label columns and number columns */
const sxShape=r=>{
  if(!r)return null;
  if(r.kind==='time'){const sr=r.spec.series,x=r.spec.x,step=x.length>1?(Date.parse(x[1])-Date.parse(x[0]))/864e5:7,v0=sr[0].values.filter(v=>v!=null);return{kind:'time',n:sr.length,rows:x.length,daily:step<=1.5,signed:v0.some(v=>v<0)&&v0.some(v=>v>0),pos:sr.slice(0,2).every(z=>z.values.every(v=>v==null||v>0))}}
  const isId=c=>/(^|_)(id|rank)$/i.test(c),T=[],N=[];
  r.cols.forEach((c,i)=>{const vals=r.rows.map(x=>x[i]);if(vals.every(v=>v==null||typeof v==='number')){if(!isId(c))N.push(i)}else T.push(i)});
  return{kind:'cat',T,N,rows:r.rows.length,pos:N.length>0&&N.every(i=>r.rows.every(x=>x[i]==null||x[i]>0))};
};
const SX_RULE={
 'Bars':s=>s.kind==='time','Line chart':s=>s.kind==='time','Area chart':s=>s.kind==='time','Step lines':s=>s.kind==='time',
 'Stacked bars':s=>s.kind==='time'&&s.n>1,'Waterfall':s=>s.kind==='time'&&s.rows<=120,'Diverging bars':s=>s.kind==='time'&&s.signed,
 'Bars with targets':s=>s.kind==='time'&&s.n>1,'Calendar stripes':s=>s.kind==='time'&&s.daily&&s.rows>=14,'Bubble scatter':s=>s.kind==='time'&&s.n>1&&s.pos,'Rank over time':s=>s.kind==='time'&&s.n>2,
 'Ranked bars':s=>s.kind==='cat'&&s.T.length>0&&s.N.length>0,'Treemap':s=>s.kind==='cat'&&s.T.length>0&&s.N.length>0&&s.pos,'Flow diagram':s=>s.kind==='cat'&&s.T.length>0&&s.N.length>0&&s.pos,
 'Stacked columns':s=>s.kind==='cat'&&s.T.length>0&&s.N.length>0&&s.pos,'Rank matrix':s=>s.kind==='cat'&&s.T.length>0&&s.N.length>1,'Bubble chart':s=>s.kind==='cat'&&s.T.length>0&&s.N.length>1&&s.pos,
 'Table':s=>!!s};
const SX_WHY={'Bars':'Needs a date column','Line chart':'Needs a date column','Area chart':'Needs a date column','Step lines':'Needs a date column','Stacked bars':'Needs a date and two or more numbers','Waterfall':'Needs a date and a change for each period, up to 120 rows','Diverging bars':'Needs a date and numbers above and below zero','Bars with targets':'Needs a date, a value and a target','Calendar stripes':'Needs one number for each day','Bubble scatter':'Needs a date and two positive numbers','Rank over time':'Needs a date and three or more numbers to rank','Ranked bars':'Needs a label and a number on each row','Treemap':'Needs a label and a positive number, with an optional group','Flow diagram':'Needs a label, or a from and a to, and a positive amount','Stacked columns':'Needs labels and positive numbers','Rank matrix':'Needs labels and two or more numbers to rank by','Bubble chart':'Needs labels and two or more positive numbers','Interactive model':'Built in code for one question, so a query cannot draw it','Compare tool':'Built in code for one question, so a query cannot draw it','Dot strip':'Built in code for one question, so a query cannot draw it','Commands':'Built in code for one question, so a query cannot draw it'};
const PLUS=svg('<path d="M12 5v14M5 12h14"/>',15);
const ICON_OK=svg('<circle cx="12" cy="12" r="9"/><path d="M8 12.4l2.7 2.7L16.2 9.6"/>',18);
const ICON_WARN=svg('<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.4v.1"/>',18);
const ICON_X=svg('<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',14);
const ICON_BLOCK=svg('<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',18);
const ICON_DATE=svg('<rect x="4" y="5.5" width="16" height="14" rx="2.5"/><path d="M4 10h16M9 3.5v4M15 3.5v4"/>',12);
/* A question in the Studio: its words, a layout, its queries and its charts. Each query has a name, its SQL and its last result.
   Each chart reads one query by its id, so charts can share one, and has a stable short name, a form with the values it shows,
   a title, a reading, sources and a text alternative. */
const ST={started:false,handles:[],last:'#sx-in-f',cur:0,charts:[],queries:[],qcur:0,base:null,pr:null,device:'desktop',sugg:null};
const SX_LAYS={'One chart':null,'One below another':'stack','Side by side':'pair','Tabs':'tabs'};
const sxA=()=>ST.aid?ANALYSES.find(x=>x.id===ST.aid):null;
const sxC=()=>ST.charts[ST.cur];
const sxQOf=c=>c?ST.queries.find(q=>q.id===c.qid):null;
const sxQ=()=>ST.queries[ST.qcur]||ST.queries[0];
const sxQName=id=>(ST.queries.find(q=>q.id===id)||{}).name||'no query';
const sxMany=()=>ST.charts.length>1;
/* Stacked charts and tabs each carry a reading and sources; charts side by side share one, as on the page */
const sxPer=()=>sxMany()&&ST.layout!=='Side by side';
const sxOwner=()=>sxPer()?sxC():sxMany()?ST:ST.charts[0];
const sxSlug=t=>String(t||'').toLowerCase().replace(/&[^;]+;/g,'').replace(/[^a-z0-9]+/g,'_').replace(/^_+|_+$/g,'').slice(0,18)||'chart';
const sxUniq=(b,skip)=>{let n=b,k=2;while(ST.charts.some(c=>c!==skip&&c.name===n))n=`${b}_${k++}`;return n};
const sxQSlug=t=>String(t||'').toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_+|_+$/g,'').slice(0,24);
const sxUniqQ=(b,skip)=>{let n=b,k=2;while(ST.queries.some(q=>q!==skip&&q.name===n))n=`${b}_${k++}`;return n};
/* A query: a name, its SQL, its last result and the editor's place in it. Its result is stale once the text differs from the text that produced it. */
function sxMkQ(o){
  const q={id:o.id||'q'+Math.random().toString(36).slice(2,7),name:o.name||'query1',sql:o.sql||'',res:o.res||null,ranSql:o.res?(o.sql||''):null,ranAt:o.res?Date.now():null,runNote:o.runNote||'',base:o.base||null,caret:null,sort:null};
  Object.defineProperty(q,'stale',{get(){return !!this.res&&this.ranSql!==this.sql}});
  return q;
}
/* A chart reads its query's SQL and result through these, so code written for a chart sees the query it links to */
const SX_QF=['sql','res','ranSql','ranAt','runNote','base','caret','sort','hist'];
function sxMk(o){
  const c={id:o.id||'c'+Math.random().toString(36).slice(2,7),name:o.name||'',label:o.label||'',key:o.key||'',qid:o.qid,form:o.form||'Bars',own:o.own||null,live:!!o.live,read:o.read||'',src:[...(o.src||[])],srcAuto:o.srcAuto,alt:o.alt||'',ends:true,enc:{off:[],label:null,value:null,top:10}};
  SX_QF.forEach(k=>Object.defineProperty(c,k,{enumerable:true,get(){const q=sxQOf(this);return q?q[k]:k==='sql'?'':null},set(v){const q=sxQOf(this);if(q)q[k]=v}}));
  Object.defineProperty(c,'stale',{get(){const q=sxQOf(this);return !!q&&q.stale}});
  return c;
}
/* The result as the chart uses it: series switched off are left out */
const sxEff=c=>{const r=c&&c.res;if(!r||r.kind!=='time'||!c.enc.off.length)return r;const keep=r.spec.series.map((s,i)=>i).filter(i=>!c.enc.off.includes(i));return{...r,cols:[r.cols[0],...keep.map(i=>r.cols[i+1])],rows:r.rows.map(x=>[x[0],...keep.map(i=>x[i+1])]),spec:{...r.spec,series:keep.map(i=>r.spec.series[i])}}};
/* For a result of labels and numbers: the label and value columns, chosen or guessed, and a second label for grouped forms */
const sxPick=r=>{const row=r.rows[0]||[],isId=c=>/(^|_)(id|rank)$/i.test(c);let li=row.findIndex(v=>typeof v==='string');if(li<0)li=0;const ci=row.findIndex((v,i)=>i!==li&&typeof v==='number'&&!isId(r.cols[i]));return{li,ci}};
const sxLV=(c,r)=>{const sh=sxShape(r),p=sxPick(r),L=c.enc.label!=null&&sh.T.includes(c.enc.label)?c.enc.label:(sh.T[0]??p.li),V=c.enc.value!=null&&sh.N.includes(c.enc.value)?c.enc.value:(sh.N[0]??p.ci);return{L,V,L2:sh.T.find(i=>i!==L)}};
const sxFitsC=(c,f)=>{if(c.live&&c.own===f&&!c.enc.off.length)return true;const sh=sxShape(sxEff(c));return !!(sh&&!c.stale&&SX_RULE[f]&&SX_RULE[f](sh))};
const sxSuggestC=c=>{const sh=sxShape(sxEff(c));return !sh?null:sh.kind==='time'?(sh.n>1?'Line chart':'Bars'):sh.T.length>1?'Treemap':sh.N.length>1?'Rank matrix':'Ranked bars'};
const sxSources=()=>[...new Set(ANALYSES.flatMap(a=>[...(a.src||[]),...(a.charts||[]).flatMap(c=>c.src||[])]))].filter(id=>VZ.sourceInfo(id));
/* The warehouse catalog (shared/catalog.js, from make catalog): each gold table, its fields, and the sources each field comes from.
   A field's tuple is [name, type, unit, description, its own sources or 0 for the table's, 1 if it is a key]. */
const SX_CAT=(window.LCAT&&LCAT.tables)||Object.fromEntries(Object.entries(LC.lineage.tables).map(([t,s])=>[t,{a:'Tables',d:'',g:[],n:null,f:null,l:null,s,c:[]}]));
const SX_AREAS=[...new Set(Object.values(SX_CAT).map(t=>t.a))],SX_NF=Object.values(SX_CAT).reduce((n,t)=>n+t.c.length,0);
const SX_MAC=/Mac|iPhone|iPad/.test(navigator.platform),SX_UNDO=SX_MAC?'⌘Z':'Ctrl+Z',SX_REDO=SX_MAC?'⇧⌘Z':'Ctrl+Y';
const sxList=a=>a.length<2?a.join(''):a.slice(0,-1).join(', ')+' and '+a[a.length-1];
const sxFirst=s=>{s=String(s||'');const m=s.match(/^.*?[a-z0-9)\]]\.(?=\s|$)/i);return m?m[0]:s};
/* SQL without comments or string literals, for finding the tables and fields a query names */
const sxStripSql=sql=>String(sql||'').replace(/--[^\n]*/g,' ').replace(/\/\*[\s\S]*?\*\//g,' ').replace(/'(?:[^']|'')*'/g,"''");
const sxReads=sql=>[...new Set([...sxStripSql(sql).matchAll(/\b(?:from|join)\s+(?:gold\.)?([a-z_][a-z0-9_]*)/gi)].map(m=>m[1].toLowerCase()).filter(t=>SX_CAT[t]))];
/* Names after from or join that are neither a table in the warehouse nor a name the query defines with "as (" */
const sxUnknown=sql=>{const s=sxStripSql(sql),own=new Set([...s.matchAll(/\b([a-z_][a-z0-9_]*)\s+as\s*\(/gi)].map(m=>m[1].toLowerCase()));return [...new Set([...s.matchAll(/\b(?:from|join)\s+(gold\.)?([a-z_][a-z0-9_]*)(?![\w.(])/gi)].map(m=>m[2].toLowerCase()).filter(t=>!SX_CAT[t]&&!own.has(t)&&t!=='gold'&&!/^(select|lateral|unnest|range|generate_series)$/.test(t)))]};
/* The sources a query reads. A field it names brings the sources it names itself, for certain, or else its table's,
   which are certain only when the table has one. Keys and dates bring none, select * reads every field, and a table
   built from other tables' rows brings only possible sources, because which ones depends on the rows kept. */
function sxQuerySrc(sql){
  const s=sxStripSql(sql).toLowerCase(),words=new Set(s.match(/[a-z_][a-z0-9_]*/g)||[]),star=/\bselect\s+(?:distinct\s+)?\*|\.\*/.test(s),out=new Map();
  const add=(ids,why,sure)=>(ids||[]).forEach(id=>{if(!VZ.sourceInfo(id))return;const o=out.get(id)||{w:[],sure:false};if(!o.w.includes(why))o.w.push(why);o.sure=o.sure||sure;out.set(id,o)});
  sxReads(sql).forEach(t=>{const T=SX_CAT[t],named=T.c.filter(c=>!c[5]&&words.has(c[0])),one=T.s.length===1&&!T.v;
    if(star||!named.length){add(T.s,`all of ${t}`,!T.v&&(star||one));if(star)T.c.forEach(c=>{if(c[4]&&!c[5])add(c[4],`all of ${t}`,!T.v)})}
    named.forEach(c=>c[4]?add(c[4],`${c[0]} in ${t}`,!T.v):add(T.s,`${c[0]} in ${t}`,one))});
  return out;
}
/* Who carries the credits: each chart when charts are stacked or tabbed, the question when they sit side by side */
const sxOwners=()=>sxPer()?ST.charts:sxMany()?[ST]:[ST.charts[0]];
const sxActualOf=o=>{if(o!==ST)return sxQuerySrc(o.sql);const m=new Map();ST.charts.forEach(c=>sxQuerySrc(c.sql).forEach((v,id)=>{const p=m.get(id);m.set(id,p?{w:[...p.w,...v.w],sure:p.sure||v.sure}:v)}));return m};
/* Credits follow the query until the editor picks them by hand. With nothing picked yet, they follow it too. */
const sxAuto=o=>o.srcAuto??!o.src.length;
const sxSyncSrc=()=>sxOwners().forEach(o=>{if(!sxAuto(o))return;o.srcAuto=true;const a=[...sxActualOf(o).keys()];if(a.join()!==o.src.join())o.src=a});
/* What the credits leave out. Only a source the query reads for certain counts against them; a possible one or an extra is the editor's call. */
const sxSrcGap=o=>{const a=sxActualOf(o),ids=[...a.keys()],miss=ids.filter(id=>a.get(id).sure&&!o.src.includes(id)),maybe=ids.filter(id=>!a.get(id).sure&&!o.src.includes(id)),extra=o.src.filter(id=>!a.has(id)),n=id=>VZ.sourceInfo(id)?VZ.sourceInfo(id).name:id;return{miss,maybe,extra,ok:!miss.length,same:!miss.length&&!maybe.length&&!extra.length,text:miss.length?`${sxList(miss.map(n))} not credited`:'All credited'}};
/* A sample query on a table: all of it, newest rows first when its grain has a date */
const sxSample=t=>{const T=SX_CAT[t],d=T&&T.c.find(c=>/^(DATE|TIMESTAMP)/.test(c[1])&&T.g.includes(c[0]));return `select *\nfrom gold.${t}${d?`\norder by ${d[0]} desc`:''}\nlimit 100;`};
const sxStarter=v=>!v.trim()||/^select\s+\*\s+from\s+gold\.\s+limit\s+100;?$/i.test(v.trim());
/* Undo for the query. A run of typing, a paste and each change a button makes are one step each, and every query keeps its own history. */
const sxHist=c=>c.hist||(c.hist={past:[],future:[],kind:'',at:0,end:-1,ws:false});
const sxPushHist=(c,st)=>{const h=sxHist(c),top=h.past[h.past.length-1];if(top&&top.v===st.v)return;h.past.push(st);if(h.past.length>200)h.past.shift()};
function sxNoteTyping(c,ta,type,data){
  const h=sxHist(c),now=Date.now(),kind=/^insert(Text|CompositionText)$/.test(type)?'type':/^delete(Content|Word|Soft|Hard)/.test(type)?'del':type,ws=typeof data==='string'&&/^\s+$/.test(data);
  const join=(kind==='type'||kind==='del')&&kind===h.kind&&now-h.at<1500&&ta.selectionStart===ta.selectionEnd&&ta.selectionStart===h.end&&!(kind==='type'&&h.ws&&!ws);
  if(!join)sxPushHist(c,{v:ta.value,s:ta.selectionStart,e:ta.selectionEnd});
  h.kind=kind;h.at=now;h.ws=ws;h.future=[];
}
function sxSetSql(c,v,s,e){
  const ta=$('#sx-sql'),was=c.stale;c.sql=v;if(ta&&ta.value!==v)ta.value=v;
  if(s!=null){c.caret=[s,e??s];if(ta&&document.activeElement===ta)ta.setSelectionRange(s,e??s)}
  sxHist(c).end=c.caret?c.caret[1]:-1;
  sxAfterSql(c,was);
}
/* A change made by a button is a step of its own */
function sxEditSql(c,v,s,e){
  if(v===c.sql)return false;
  sxPushHist(c,{v:c.sql,s:c.caret?c.caret[0]:c.sql.length,e:c.caret?c.caret[1]:c.sql.length});
  const h=sxHist(c);h.future=[];h.kind='';
  sxSetSql(c,v,s,e);return true;
}
function sxUndo(redo){
  const c=sxQ(),h=sxHist(c),ta=$('#sx-sql'),from=redo?h.future:h.past,to=redo?h.past:h.future;
  let st=from.pop();while(st&&st.v===c.sql)st=from.pop();
  if(!st)return;
  to.push({v:c.sql,s:ta?ta.selectionStart:c.sql.length,e:ta?ta.selectionEnd:c.sql.length});h.kind='';h.at=0;const fl=$('#sx-flash');if(fl)fl.innerHTML='';
  sxSetSql(c,st.v,st.s,st.e);
}
/* Whatever changed the query, the same things follow: the highlighting at once, and the rest once typing pauses */
let sxQT=0;
function sxAfterSql(c,was){
  $('#sx-hl').innerHTML=sxHl(c.sql);
  if(c.stale!==was){const ta=$('#sx-sql'),f=document.activeElement===ta,s=ta.selectionStart,e=ta.selectionEnd;sxPaintCharts();sxPaintQuery();sxPaintChart();sxPaintWords();sxPaintPreview();sxPaintChecks();if(f){ta.focus({preventScroll:true});ta.setSelectionRange(s,e)}}
  clearTimeout(sxQT);sxQT=setTimeout(()=>{if(!$('#sx-sql'))return;sxQueryMeta();if(ST.tblSel||sxReads(sxQ().sql).join()!==ST.readsKey)sxPaintTables();const before=JSON.stringify(sxOwners().map(o=>o.src));sxPaintSources();if(JSON.stringify(sxOwners().map(o=>o.src))!==before)sxPaintPreview();sxPaintChecks()},250);
}
/* Into the editor at the cursor. Without one yet: an empty "from gold." takes a table, and anything else goes at the end.
   A field right after another becomes a list, and a field right after "select *" takes the star's place. */
const SX_ENDKW=/\b(select|distinct|from|join|where|and|or|on|by|as|having|when|then|else|case|not|in|is|like|between|limit|over|partition|with|union|all|order|group|desc|asc)$/i;
let sxFT=0;
function sxFlash(c,a,b){const f=$('#sx-flash');if(!f)return;const v=c.sql;f.innerHTML=sxEsc(v.slice(0,a))+`<mark>${sxEsc(v.slice(a,b))}</mark>`+sxEsc(v.slice(b))+'\n';clearTimeout(sxFT);sxFT=setTimeout(()=>{f.innerHTML=''},1500)}
function sxInsert(c,text,isTable,keep){
  const v=c.sql;let s,e,pre='';
  if(c.caret){s=Math.min(c.caret[0],v.length);e=Math.min(c.caret[1],v.length)}
  else{const m=isTable&&/\b(?:from|join)\s+gold\.(?![a-z0-9_])/i.exec(v);if(m)s=e=m.index+m[0].length;else{s=e=v.length;if(v&&!/\n$/.test(v))pre='\n'}}
  let b=v.slice(0,s);const after=v.slice(e),core=isTable&&/gold\.$/i.test(b)?text.replace(/^gold\./,''):text;let ins=core;
  if(!isTable&&!pre){if(/\bselect\s+\*$/i.test(b))b=b.slice(0,-1);else{const tb=b.replace(/[ \t]+$/,'');if(/[\w)]$/.test(tb)&&!SX_ENDKW.test(tb)){b=tb;ins=', '+ins}}}
  if(!pre&&b&&!/[\s(,.]$/.test(b)&&!/^,/.test(ins))ins=' '+ins;
  if(after&&!/^[\s),;]/.test(after))ins+=' ';
  ins=pre+ins;const at=b.length+ins.length,from=b.length+ins.indexOf(core);
  sxEditSql(c,b+ins+after,at,at);sxFlash(c,from,from+core.length);
  const say=$('#sx-live');if(say)say.textContent=`${core} is in the query.`;
  if(!keep)sxFocusSql();
}
function sxFocusSql(){
  const ta=$('#sx-sql'),c=sxQ(),box=ta.closest('.sx-code');ta.focus({preventScroll:true});if(c.caret)ta.setSelectionRange(c.caret[0],c.caret[1]);
  const r=box.getBoundingClientRect();if(r.top>innerHeight-60||r.bottom<80)box.scrollIntoView({block:'nearest',behavior:LCC.reduce()?'auto':'smooth'});
}
const sxAsOf=c=>{const r=sxEff(c);if(!r)return null;if(r.kind!=='time')return r.asOf||LC.asOf;const v=r.spec.series[0].values;let i=v.length-1;while(i>0&&v[i]==null)i--;return r.spec.x[i]};
const sxAgo=t=>{if(!t)return'';const s=Math.round((Date.now()-t)/1000);return s<45?'Ran just now':s<90?'Ran a minute ago':s<3600?`Ran ${Math.round(s/60)} minutes ago`:'Ran over an hour ago'};
/* The fixed set of values a chart offers to the words, all computed from its result */
function sxTokensOf(c){
  const r=sxEff(c);if(!r||c.stale)return{};
  if(r.kind==='time'){
    const sp=r.spec,s=sp.series[0],v=s.values,x=sp.x;let li=v.length-1;while(li>0&&v[li]==null)li--;let pi=li-1;while(pi>0&&v[pi]==null)pi--;
    const F=sp.tipFmt||(n=>sxFmt(r.cols[1],n)),pk=d3.maxIndex(v),lo=d3.minIndex(v),cur=v[li],prev=pi>=0?v[pi]:null,ch=prev!=null?cur-prev:null,chp=prev?ch/Math.abs(prev):null,step=(Date.parse(x[Math.min(1,x.length-1)])-Date.parse(x[0]))/864e5;
    const dir=ch==null||Math.abs(chp||0)<.005?'held':ch>0?'rose':'fell';
    const T={series:[s.name,'Series'],latest:[F(cur),'Latest'],previous:[prev!=null?F(prev):'n/a','The one before'],change:[ch!=null?(ch>=0?'+':'−')+F(Math.abs(ch)):'n/a','Change'],change_pct:[chp!=null?(chp>=0?'+':'−')+fmt.pct(Math.abs(chp),Math.abs(chp)<.1?1:0):'n/a','Change, %'],direction:[dir,'Direction'],peak:[F(v[pk]),'Peak'],peak_date:[dm(x[pk]),'Peak date'],low:[F(v[lo]),'Low'],as_of:[dm(x[li]),'As of'],period:[step>25?'month':step>5?'week':'day','Period']};
    T.name=T.series;T.latest_date=T.as_of;
    return T;
  }
  const {L,V}=sxLV(c,r),rows=sxTop(r,L,V,0).rows,tot=d3.sum(rows,x=>x[V]),top=rows[0]||[],sec=rows[1]||[];
  return{top:[String(top[L]??''),`First ${r.cols[L]}`],top_value:[V>=0?sxFmt(r.cols[V],top[V]):'',r.cols[V]||'Value'],top_share:[tot?fmt.pct(top[V]/tot,0):'n/a','Its share'],second:[String(sec[L]??''),'Second'],total:[sxFmt(r.cols[V],tot),'Total'],rows:[fmt.int(r.rows.length),'Rows'],as_of:[dm(LC.asOf),'As of']};
}
const SX_HIDE=['name','latest_date'];
/* {{latest}} reads the chart the text belongs to, {{fees.latest}} reads the chart named fees. {{2.latest}} is a typing shortcut, rewritten to the name. */
const SX_TOK=/\{\{\s*(?:([a-z0-9_]+)\.)?([a-z_]+)\s*\}\}/g;
const sxChartBy=(ref,ci)=>ref==null?ST.charts[ci]:/^\d+$/.test(ref)?ST.charts[+ref-1]:ST.charts.find(c=>c.name===ref);
const sxFill=(t,ci=0)=>String(t||'').replace(SX_TOK,(m,ref,k)=>{const c=sxChartBy(ref,ci),T=c?sxTokensOf(c):{};return T[k]?T[k][0]:m});
const sxFillHtml=(t,ci=0)=>sxEsc(t||'').replace(SX_TOK,(m,ref,k)=>{const c=sxChartBy(ref,ci),T=c?sxTokensOf(c):{};return T[k]?`<span class="sx-tv" title="${m}">${sxEsc(T[k][0])}</span>`:`<span class="sx-bad" title="This value does not resolve">${m}</span>`});
const sxUnresolved=(t,ci=0)=>[...String(t||'').matchAll(SX_TOK)].filter(([m,ref,k])=>{const c=sxChartBy(ref,ci);return !c||!sxTokensOf(c)[k]}).map(x=>x[0]);
const sxNameRefs=t=>String(t||'').replace(/\{\{\s*(\d+)\.([a-z_]+)\s*\}\}/g,(m,n,k)=>{const c=ST.charts[+n-1];return c?`{{${c.name}.${k}}}`:m});
/* Numbers typed by hand, outside values; years and numbers inside names such as HSP-029 are left alone */
const sxBare=t=>(String(t||'').replace(SX_TOK,' ').match(/(?<![\w\-.$])\$?\d[\d,.]*\s?%?(?![\w\-])/g)||[]).filter(n=>!/^(19|20)\d\d$/.test(n.trim()));
const SX_UP=/\b(rose|rises|rising|grew|grows|growing|increased|climbed|up|higher|gained)\b/i,SX_DOWN=/\b(fell|falls|falling|dropped|declined|shrank|down|lower|slipped)\b/i;
/* The texts of the question, each with the chart its bare values read from */
const sxTexts=()=>[['Question',ST.q,0,'#sx-in-q'],['Headline',ST.f,0,'#sx-in-f'],['Answer',ST.av,0,'#sx-in-av'],['Answer label',ST.al,0,'#sx-in-al'],['Shared reading',ST.read,0,'#sx-in-r'],...ST.charts.flatMap((c,i)=>[[`Chart ${i+1} title`,c.label,i,'#sx-in-cl'],[`Chart ${i+1} key figure`,c.key,i,'#sx-in-ck'],[`Chart ${i+1} reading`,c.read,i,'#sx-in-r'],[`Chart ${i+1} text alternative`,c.alt,i,'#sx-in-alt']])];
const sxSnap=()=>JSON.parse(JSON.stringify({q:ST.q,f:ST.f,av:ST.av,al:ST.al,layout:ST.layout,read:ST.read,src:ST.src,queries:ST.queries.map(q=>({id:q.id,name:q.name,sql:q.sql})),charts:ST.charts.map(c=>({id:c.id,name:c.name,label:c.label,key:c.key,qid:c.qid,form:c.form,read:c.read,src:c.src,alt:c.alt,enc:c.enc}))}));
/* What changed against the published version, in words a reviewer can read */
function sxChanges(base){
  const b=base||ST.base,out=[];
  if(!b){const q=ST.queries.filter(x=>ST.charts.some(c=>c.qid===x.id)).length;return[['A',`New question with ${ST.charts.length===1?'one chart':ST.charts.length+' charts'}, reading ${q===1?'one query':q+' queries'}`]]}
  const same=(x,y)=>JSON.stringify(x)===JSON.stringify(y);
  if(b.q!==ST.q)out.push(['M','Question reworded']);if(b.f!==ST.f)out.push(['M','Headline edited']);if(b.av!==ST.av||b.al!==ST.al)out.push(['M','Answer on the question card edited']);
  if(b.layout!==ST.layout)out.push(['M',`Charts now sit ${ST.layout.toLowerCase()}, not ${b.layout.toLowerCase()}`]);
  if(b.read!==ST.read)out.push(['M','Shared reading edited']);if(!same(b.src,ST.src))out.push(['M','Shared sources changed']);
  const bq=b.queries||[];
  ST.queries.forEach(q=>{const o=bq.find(x=>x.id===q.id);if(!o){out.push(['A',`Query ${q.name} added`]);return}if(o.name!==q.name)out.push(['M',`Query ${o.name} renamed ${q.name}`]);if(o.sql!==q.sql)out.push(['M',`Query ${q.name} edited`])});
  bq.forEach(o=>{if(!ST.queries.some(q=>q.id===o.id))out.push(['D',`Query ${o.name} removed`])});
  ST.charts.forEach((c,i)=>{const o=b.charts.find(x=>x.id===c.id),w=`Chart ${i+1}, ${c.label||c.name}`;if(!o){out.push(['A',`${w}, added`]);return}
    if(o.form!==c.form)out.push(['M',`${w}: ${o.form} became ${c.form}`]);if(o.qid!==c.qid)out.push(['M',`${w}: now reads ${sxQName(c.qid)}`]);if(o.label!==c.label)out.push(['M',`${w}: title edited`]);if(o.key!==c.key)out.push(['M',`${w}: key figure edited`]);if(o.read!==c.read)out.push(['M',`${w}: reading edited`]);if(!same(o.src,c.src))out.push(['M',`${w}: sources changed`]);if(o.alt!==c.alt)out.push([o.alt?'M':'A',`${w}: text alternative ${o.alt?'edited':'added'}`]);if(!same(o.enc,c.enc))out.push(['M',`${w}: values shown changed`]);if(o.name!==c.name)out.push(['M',`${w}: short name ${o.name} became ${c.name}`])});
  b.charts.forEach(o=>{if(!ST.charts.some(c=>c.id===o.id))out.push(['D',`${o.label||o.name} removed`])});
  return out;
}
/* Only text that differs from the published version is checked for typed numbers; a draft is checked in full */
const sxEdited=()=>{const b=ST.base;return sxTexts().filter(([lab,t,i])=>{if(!t)return false;if(!b)return true;if(lab==='Question')return t!==b.q;if(lab==='Headline')return t!==b.f;if(lab==='Answer')return t!==b.av;if(lab==='Answer label')return t!==b.al;if(lab==='Shared reading')return t!==b.read;const o=b.charts.find(x=>x.id===ST.charts[i].id);if(!o)return true;return /title$/.test(lab)?t!==o.label:/key figure$/.test(lab)?t!==o.key:/reading$/.test(lab)?t!==o.read:t!==o.alt})};
/* Direction words that contradict the latest change in the chart a text reads */
function sxDirIssues(){
  const out=[];
  sxTexts().forEach(([lab,t,i])=>{if(!t||/title|alternative/.test(lab))return;const ref=[...String(t).matchAll(SX_TOK)].map(m=>m[1]).find(Boolean),c=ref?sxChartBy(ref,i):ST.charts[i],T=c?sxTokensOf(c):{};if(!T.direction)return;const plain=sxFill(t,i),d=T.direction[0];
    if(d==='fell'&&SX_UP.test(plain))out.push(`${lab} says "${plain.match(SX_UP)[0]}", but ${T.series[0].toLowerCase()} fell ${T.change_pct[0].replace(/^[−+]/,'')}`);
    if(d==='rose'&&SX_DOWN.test(plain))out.push(`${lab} says "${plain.match(SX_DOWN)[0]}", but ${T.series[0].toLowerCase()} rose ${T.change_pct[0].replace(/^[−+]/,'')}`)});
  return out;
}
/* Checks in two tiers: blocking ones stop the pull request, warnings travel in it */
function sxChecks(){
  sxSyncSrc();
  const cs=ST.charts,many=sxMany(),per=sxPer(),wc=t=>(String(t).match(/\S+/g)||[]).length,B=[],W=[];
  const used=ST.queries.filter(q=>cs.some(c=>c.qid===q.id)),ran=used.filter(q=>q.res&&q.res.rows.length&&!q.stale).length,u0=used[0];
  B.push([ran===used.length,used.length>1?'Every query a chart reads has run and returned rows':'The query has run and returned rows',used.length>1?`${ran} of ${used.length}`:u0&&u0.stale?'Changed since it ran':u0&&u0.res?`${fmt.int(u0.res.rows.length)} rows`:'Not run','sx-q']);
  const fit=cs.filter(c=>sxFitsC(c,c.form)).length;
  B.push([fit===cs.length,many?'Every chart fits its result':'The chart fits its result',many?`${fit} of ${cs.length}`:cs[0].form,'sx-c']);
  const bad=[...new Set(sxTexts().flatMap(([lab,t,i])=>sxUnresolved(t,i)))];
  B.push([!bad.length,'Every value resolves',bad.length?bad.slice(0,2).join(', '):'All resolve','sx-w']);
  if(many){const t=cs.filter(c=>c.label.trim()).length;B.push([t===cs.length,'Every chart has a title',`${t} of ${cs.length}`,'sx-in-cl'])}
  const alt=cs.filter(c=>c.alt.trim()).length;
  B.push([alt===cs.length,many?'Every chart has a text alternative':'The chart has a text alternative',many?`${alt} of ${cs.length}`:alt?'Written':'Missing','sx-in-alt']);
  const srcs=per?cs.map(c=>c.src.length):[sxOwner().src.length],sok=srcs.filter(k=>k>0).length;
  B.push([sok===srcs.length,srcs.length>1?'Each chart credits its sources':'Its sources are credited',srcs.length>1?`${sok} of ${srcs.length}`:`${srcs[0]} picked`,'sx-srcs']);
  B.push([/\?\s*$/.test(ST.q),'The question ends with a question mark',ST.q.trim()?'':'Empty','sx-in-q']);
  const reads=per?cs.map((c,i)=>[c.read,i]):[[sxOwner().read,0]],has=reads.filter(([t])=>String(t).trim()).length;
  B.push([has===reads.length,reads.length>1?'Each chart has a reading':'There is a reading',reads.length>1?`${has} of ${reads.length}`:has?'Written':'Empty','sx-in-r']);
  const rok=reads.filter(([t,i])=>{const n=wc(sxFill(t,i));return n>=15&&n<=70}).length;
  W.push([rok===reads.length,reads.length>1?'Each reading runs 15 to 70 words':'The reading runs 15 to 70 words',reads.length>1?`${rok} of ${reads.length}`:`${wc(sxFill(reads[0][0],0))} words`,'sx-in-r']);
  const typed=sxEdited().reduce((n,[,t])=>n+sxBare(t).length,0);
  W.push([!typed,'Numbers come from values, not typing',typed?`${typed} typed`:'None typed','sx-w']);
  const dir=sxDirIssues();W.push([!dir.length,'Direction words match the data',dir.length?dir[0]:'They agree','sx-w']);
  const os=sxOwners(),gaps=os.map(sxSrcGap),sm=gaps.filter(g=>g.ok).length;
  W.push([sm===os.length,os.length>1?'Each chart credits the sources its query reads':'Every source the query reads is credited',os.length>1?`${sm} of ${os.length}`:gaps[0].text,'sx-srcs']);
  const idle=ST.queries.filter(q=>!cs.some(c=>c.qid===q.id));W.push([!idle.length,'Every query feeds a chart',idle.length?`${sxList(idle.map(q=>q.name))} ${idle.length===1?'feeds none and is':'feed none and are'} left out`:'All feed one','sx-q']);
  if(many&&ST.layout==='Side by side'){const amb=[...String(ST.read).matchAll(/\{\{\s*([a-z_]+)\s*\}\}/g)].length;W.push([!amb,'The shared reading names a chart in each value',amb?`${amb} without a chart name`:'All named','sx-in-r'])}
  return{B,W,blocks:B.filter(x=>!x[0]).length,warns:W.filter(x=>!x[0]).length};
}
function sxDraft(sid){
  const list=inSubject(sid).filter(isLive),find=want=>{for(const a of list){const cs=chartsOf(a);for(let i=0;i<cs.length;i++){const r=sxChartResult(a,cs[i],i);if(r&&(!want||r.kind===want))return{a,c:cs[i],i,r}}}return null};
  const b=find('time')||find(null);
  const q=sxMkQ({name:'query1',sql:b?(b.c.sql||b.a.sql||''):'select *\nfrom gold.\nlimit 100;',res:b?b.r:null,runNote:b?'':'Write a query that reads a table, then run it.',base:b?{aid:b.a.id,ci:b.i}:null});
  ST.queries=[q];ST.qcur=0;
  const c=sxMk({name:'chart1',qid:q.id,src:[],srcAuto:true});
  c.form=sxSuggestC(c)||'Bars';
  Object.assign(ST,{sid,open:sid,aid:null,layout:'One chart',cur:0,charts:[c],read:'',src:[],srcAuto:true,base:null,pr:null,sugg:null});
  /* A starter the editor rewrites: worded so it reads correctly for any series name */
  if(b&&b.r.kind==='time'){const x=b.r.spec.x,step=(Date.parse(x[Math.min(1,x.length-1)])-Date.parse(x[0]))/864e5,per=step>25?'month':step>5?'week':'day';Object.assign(ST,{q:`How does the latest ${per} compare with the peak?`,f:'The latest {{period}} came in at {{latest}}, against a peak of {{peak}} on {{peak_date}}',av:'{{latest}}',al:'in the latest {{period}}'})}
  else if(b)Object.assign(ST,{q:'What comes first, and by how much?',f:'{{top}} comes first, with {{top_value}}',av:'{{top_value}}',al:'{{top}}'});
  else Object.assign(ST,{q:'',f:'',av:'',al:''});
  c.alt=sxAltDraft(c);
}
function sxLoad(aid){
  const a=ANALYSES.find(x=>x.id===aid),live=isLive(a),cs=chartsOf(a),many=!!a.charts;
  const plannedSql=()=>/^[\w.]+$/.test(a.table||'')?`select *\nfrom ${a.table}\nlimit 100;`:`-- Planned: ${a.table}\nselect *\nfrom gold.\nlimit 100;`;
  /* One query per published chart, named query1, query2 and so on; the editor can rename them, or point charts at one */
  const qs=[],charts=cs.map((c,i)=>{const res=live?sxChartResult(a,c,i):null,q=sxMkQ({name:`query${i+1}`,sql:c.sql||plannedSql(),res,runNote:live?(res?'':'This preview of the Studio has no sample rows for this chart. In a full build its query runs on the warehouse.'):'This table is planned, so it has no rows in the warehouse yet.',base:{aid,ci:i}});qs.push(q);
    return sxMk({id:many?c.id:'main',name:many?sxSlug(c.id):'chart1',label:many?c.label:'',key:many?c.key:'',qid:q.id,form:c.form||a.form,own:c.form||a.form,live,read:c.read||'',src:c.src||[]})});
  ST.queries=qs;ST.qcur=0;
  Object.assign(ST,{sid:a.subject,open:a.subject,aid,cur:0,charts,layout:many?({tabs:'Tabs',pair:'Side by side',stack:'One below another'}[a.layout]||'Tabs'):'One chart',q:a.q,f:live?(a.f||''):'',av:a.ans?a.ans[0]:'',al:a.ans?a.ans[1]:'',read:a.layout==='pair'?(a.read||''):'',src:a.layout==='pair'?[...(a.src||[])]:[],srcAuto:undefined,pr:null,sugg:null});
  sxSyncSrc();ST.base=live?sxSnap():null;
}
/* Work in progress. Every question opened in the Studio keeps its working copy, so leaving it for the home page or for
   another question loses nothing. A copy with no edits and no pull request is dropped. */
const SX_WORK=['sid','aid','layout','cur','qcur','charts','queries','q','f','av','al','read','src','srcAuto','base','pr','sugg','step','snap0'];
ST.work=new Map();ST.key=null;ST.seq=0;
const sxMark0=()=>{ST.snap0=JSON.stringify(sxSnap())};
function sxStash(){
  if(!ST.key)return;
  if(JSON.stringify(sxSnap())===ST.snap0&&!ST.pr){ST.work.delete(ST.key);return}
  const o={},a=sxA();SX_WORK.forEach(k=>o[k]=ST[k]);
  o.sum={q:ST.q,sid:ST.sid,aid:ST.aid,isNew:!ST.aid,planned:!!a&&!isLive(a),n:a&&isLive(a)?sxChanges().length:0,pr:!!ST.pr,states:SX_STEPS.map(x=>sxStepState(x[0]).tone),at:Date.now()};
  ST.work.set(ST.key,o);
}
function sxResume(key){const o=ST.work.get(key);if(!o)return false;SX_WORK.forEach(k=>ST[k]=o[k]);ST.key=key;return true}
function sxOpenQ(aid){sxStash();if(ST.key===aid)return;if(!sxResume(aid)){sxLoad(aid);ST.key=aid;ST.step='query';sxMark0()}}
function sxNewQ(sid){sxStash();sxDraft(sid);ST.key='new'+(++ST.seq);ST.step='query';sxMark0()}
/* Drafts written from the result use values only, so no number is typed. They arrive as a suggestion to accept or dismiss. */
function sxReadDraft(c){
  const T=sxTokensOf(c);if(!T.latest&&!T.top)return'';const p=sxMany()?`${c.name}.`:'';
  if(T.latest)return `{{${p}series}} ${T.direction[0]==='held'?'held at':`{{${p}direction}} to`} {{${p}latest}} in the latest {{${p}period}}${T.direction[0]==='held'?'':` ({{${p}change_pct}} on the {{${p}period}} before)`}, against a peak of {{${p}peak}} on {{${p}peak_date}}. The lowest {{${p}period}} on record here was {{${p}low}}.`;
  return `{{${p}top}} comes first with {{${p}top_value}}, {{${p}top_share}} of the {{${p}total}} total, ahead of {{${p}second}}.`;
}
function sxAltDraft(c){
  const T=sxTokensOf(c);if(!T.latest&&!T.top)return'';const p=sxMany()?`${c.name}.`:'',form=c.form.toLowerCase();
  const kind={'Bars':'Bar chart','Stacked bars':'Stacked bar chart','Ranked bars':'Ranked bar chart','Step lines':'Step line chart','Diverging bars':'Diverging bar chart','Bars with targets':'Bar chart with targets','Calendar stripes':'Calendar of daily stripes','Bubble scatter':'Scatter chart','Rank over time':'Rank chart','Stacked columns':'Stacked column chart','Table':'Table'}[c.form]||c.form;
  if(T.latest)return `${kind} of {{${p}series}} by {{${p}period}}, up to {{${p}as_of}}. The latest {{${p}period}} is {{${p}latest}}, and the peak was {{${p}peak}} on {{${p}peak_date}}.`;
  const words=k=>String(k||'').replace(/_(usd|near)$/,' in $1').replace(/_/g,' ').replace(/ usd\b/,' in USD');
  return `${kind} of ${sxEsc(words(c.res.cols[sxLV(c,c.res).V])||'values')} by ${sxEsc(words(c.res.cols[sxLV(c,c.res).L])||'label')}. {{${p}top}} comes first with {{${p}top_value}}, {{${p}top_share}} of the total.`;
}
function sxRun(selected){
  const c=sxQ(),q=selected||c.sql,t=((q.match(/from\s+((?:gold\.)?[a-z][a-z0-9_]{2,})\b/i)||[])[1]||'').replace(/^gold\./,''),hits=[];
  if(t)ANALYSES.filter(isLive).forEach(a=>chartsOf(a).forEach((ch,i)=>{const tb=(ch.table||'').split(/,\s*/).map(x=>x.replace(/^gold\./,''));if(tb.includes(t)){const r=sxChartResult(a,ch,i);if(r)hits.push({a,i,r})}}));
  const pick=hits.find(h=>c.base&&h.a.id===c.base.aid&&h.i===c.base.ci)||hits[0];
  c.res=pick?pick.r:null;c.ranSql=c.sql;c.ranAt=Date.now();c.sort=null;
  c.runNote=pick?'':t?`This preview of the Studio has no sample rows for ${t}. In a full build this query runs on the warehouse.`:'Write a query that reads a table, then run it.';
  /* Each chart that reads this query starts again from the new result, and keeps its form while it still fits */
  ST.charts.filter(x=>x.qid===c.id).forEach(x=>{x.enc={off:[],label:null,value:null,top:10};if(x.res&&!sxFitsC(x,x.form))x.form=sxSuggestC(x)||x.form});
  sxPaint();
}
/* A tidy layout for SQL: one clause per line, strings left untouched */
const sxFormat=sql=>sql.split(/('(?:[^']|'')*')/).map((p,i)=>i%2?p:p.replace(/[ \t]+/g,' ').replace(/\s*\n\s*/g,' ').replace(/\s*\b(from|where|group by|order by|limit|having|left join|inner join|join|union all|union)\b\s*/gi,(m,k)=>'\n'+k.toLowerCase()+' ').replace(/\s*,\s*/g,', ')).join('').replace(/^\s+/,'').replace(/[ \t]+\n/g,'\n');
/* A waterfall builds a running total from each period's change */
function sxWaterfall(el,{x,values,fmtV,name}){
  const hue=subj(ST.sid).hue;let run=0;const base=[],up=[],down=[];
  values.forEach(v=>{v=v||0;if(v>=0){base.push(run);up.push(v);down.push(null)}else{base.push(run+v);up.push(null);down.push(-v)}run+=v});
  return VZ.echart(el,260,t=>({...LCC.baseOption(t),grid:{left:4,right:10,top:10,bottom:2,containLabel:true},
   tooltip:{...LCC.tooltipBase(t),trigger:'axis',axisPointer:{type:'shadow'},formatter:ps=>{const i=ps[0].dataIndex;return `<div class="lcc-tip-head">${dm(x[i])}</div><div class="lcc-tip-row"><span>${sxEsc(name)}</span><b>${fmtV(values[i]||0)}</b></div><div class="lcc-tip-row"><span>Running total</span><b>${fmtV(base[i]+(up[i]||0))}</b></div>`}},
   xAxis:{type:'category',data:x.map(d=>dm(d)),axisLine:{lineStyle:{color:t.grid}},axisTick:{show:false},axisLabel:{...LCC.axisText(t),hideOverlap:true}},
   yAxis:{type:'value',splitNumber:4,axisLine:{show:false},axisTick:{show:false},splitLine:{lineStyle:{color:t.grid}},axisLabel:{...LCC.axisText(t),formatter:v=>fmtV(v)}},
   series:[{type:'bar',stack:'w',data:base,silent:true,itemStyle:{color:'transparent'}},{type:'bar',stack:'w',data:up,itemStyle:{color:hue,borderRadius:[3,3,0,0]}},{type:'bar',stack:'w',data:down,itemStyle:{color:'#e5604f',borderRadius:[3,3,0,0]}}]}));
}
const sxLast=v=>{for(let i=v.length-1;i>=0;i--)if(v[i]!=null)return v[i];return null};
/* Top N rows by value, with the rest summed as Other so nothing is silently dropped */
/* Rows that share a label are summed first, so a label never appears twice */
const sxTop=(r,L,V,n)=>{const N=sxShape(r).N,g=d3.groups(r.rows.filter(x=>x[V]!=null),x=>String(x[L])).map(([k,rs])=>{const o=[];o[L]=k;N.forEach(j=>{o[j]=d3.sum(rs,x=>x[j]||0)});return o}).sort((a,b)=>b[V]-a[V]);if(!n||g.length<=n)return{rows:g,cut:0};const keep=g.slice(0,n),rest=g.slice(n),o=[];o[L]=`Other (${rest.length})`;N.forEach(j=>{o[j]=d3.sum(rest,x=>x[j]||0)});return{rows:[...keep,o],cut:rest.length}};
/* How chart i of the question is drawn: its own component while its form and values are unchanged, otherwise the form picked */
function sxViewFor(i){
  const c=ST.charts[i],r=sxEff(c),f=c.form,hue=subj(ST.sid).hue;
  if(c.live&&c.own===f&&!c.stale&&c.base&&!c.enc.off.length){const oc=chartsOf(ANALYSES.find(x=>x.id===c.base.aid))[c.base.ci];if(oc&&oc.view)return oc.view}
  if(!r||c.stale)return el=>{el.innerHTML=`<p class="sx-empty">${c.stale?'Run the query to redraw this chart.':c.runNote||'The chart appears once the query returns rows.'}</p>`};
  if(!sxFitsC(c,f))return el=>{el.innerHTML=`<p class="sx-empty">${SX_WHY[f]||'This form needs a different result'}.</p>`};
  if(f==='Table')return el=>{el.innerHTML=sxTable(r,8)};
  if(r.kind==='time'){
    const sp=r.spec,F=sp.tipFmt||(v=>sxFmt(r.cols[1],v)),s0=sp.series[0];
    /* Every series gets a colour: the subject's hue first, then the categorical order */
    if(SX_TIME[f])return el=>timeChart(el,{...sp,series:sp.series.map((z,j)=>({...z,color:z.color||(j?SX_PAL[j%8]:hue)})),type:SX_TIME[f],step:f==='Step lines',endLabels:c.ends&&/Line|Area|Step/.test(f),height:250});
    if(f==='Calendar stripes')return el=>VZ.calendar(el,{d:sp.x,v:s0.values.map(v=>v||0),fmtV:F});
    if(f==='Diverging bars')return el=>VZ.divergingBars(el,{x:sp.x,values:s0.values,height:250,posLabel:'Above zero',negLabel:'Below zero',tipLabel:s0.name,fmtTip:F,fmtAxis:F});
    if(f==='Waterfall')return el=>sxWaterfall(el,{x:sp.x,values:s0.values,fmtV:F,name:s0.name});
    if(f==='Bars with targets'){const n=Math.min(10,sp.x.length),o=sp.x.length-n;return el=>VZ.targetBars(el,[...sp.x.slice(o).map((d,k)=>({label:dm(d),value:s0.values[o+k],tip:`${dm(d)}: ${F(s0.values[o+k])}`})),...sp.series.slice(1,3).map(z=>{const v=sxLast(z.values);return{label:z.name,value:v,dashed:true,show:true,tip:`${sxEsc(z.name)}: ${F(v)}`}})],{fmtV:F,hue,height:260})}
    if(f==='Bubble scatter'){const s1=sp.series[1],s2=sp.series[2];return el=>VZ.diagonalScatter(el,{points:sp.x.map((d,k)=>({x:s0.values[k],y:s1.values[k],size:s2?Math.max(1,s2.values[k]||1):1,kind:k>=sp.x.length-6?2:1,tip:`${dm(d)}<br>${sxEsc(s0.name)} <b>${F(s0.values[k])}</b><br>${sxEsc(s1.name)} <b>${F(s1.values[k])}</b>`})).filter(p=>p.x>0&&p.y>0),lines:[],xLabel:s0.name,yLabel:s1.name,height:300,hue,fmtX:F,fmtY:F})}
    if(f==='Rank over time'){const k=Math.max(1,Math.ceil(sp.x.length/24)),idx=d3.range(sp.x.length-1,-1,-k).reverse();return el=>VZ.bump(el,{x:idx.map(j=>sp.x[j]),count:sp.series.length,height:280,highlight:'s0',fmtTip:d=>dm(d),series:sp.series.map((z,j)=>({key:'s'+j,name:z.name,color:SX_PAL[j%8],values:idx.map(q=>{const v=z.values[q];return v==null?null:1+sp.series.filter(o=>o.values[q]!=null&&o.values[q]>v).length})}))})}
  }
  const sh=sxShape(r),{L,V,L2}=sxLV(c,r),FV=j=>v=>sxFmt(r.cols[j],v),lab=x=>String(x).slice(0,48),N=c.enc.top;
  if(f==='Ranked bars'){const {rows}=sxTop(r,L,V,N);return el=>hbars(el,rows.map(x=>({label:lab(x[L]),value:+x[V]})),{fmtV:FV(V),labelWidth:130})}
  if(f==='Treemap'){
    const gs=L2!=null?d3.rollups(r.rows.filter(x=>x[V]>0),v=>v.map(x=>({name:lab(x[L2]),value:x[V]})),x=>String(x[L])).sort((a,b)=>d3.sum(b[1],q=>q.value)-d3.sum(a[1],q=>q.value)):[['All',sxTop(r,L,V,N).rows.filter(x=>x[V]>0).map(x=>({name:lab(x[L]),value:x[V]}))]];
    return el=>VZ.treemap(el,{children:gs.slice(0,N||8).map(([name,children],k)=>({name,hue:SX_PAL[k%8],children}))},{height:300,phoneHeight:320,fmtV:FV(V)});
  }
  if(f==='Flow diagram'){
    let links;
    if(L2!=null){links=d3.rollups(r.rows.filter(x=>x[V]>0),v=>d3.sum(v,x=>x[V]),x=>String(x[L]),x=>String(x[L2])).flatMap(([a,bs])=>bs.map(([b,v])=>({source:a,target:b===a?b+' ':b,value:v}))).sort((p,q)=>q.value-p.value).slice(0,Math.max(6,N||14))}
    else{const tot=r.cols[V];links=sxTop(r,L,V,N).rows.filter(x=>x[V]>0).map(x=>({source:tot,target:lab(x[L]),value:x[V]}))}
    const names=[...new Set(links.flatMap(l=>[l.source,l.target]))];
    return el=>VZ.sankey(el,{nodes:names.map((n,k)=>({name:n,itemStyle:{color:SX_PAL[k%8]}})),links,height:300,fmtV:FV(V)});
  }
  if(f==='Stacked columns'){
    let cols;
    if(L2!=null&&sh.N.length===1){const keys=[...new Set(r.rows.map(x=>String(x[L])))].slice(0,8);cols=[...new Set(r.rows.map(x=>String(x[L2])))].slice(0,5).map(cn=>({title:cn,segments:keys.map((k,j)=>({label:k,color:SX_PAL[j%8],value:d3.sum(r.rows.filter(x=>String(x[L])===k&&String(x[L2])===cn),x=>x[V]||0)})).filter(z=>z.value>0)}))}
    else{const top=sxTop(r,L,V,Math.min(N||6,6)).rows;cols=sh.N.slice(0,4).map(j=>({title:r.cols[j],segments:top.map((x,q)=>({label:lab(x[L]),color:SX_PAL[q%8],value:x[j]||0})).filter(z=>z.value>0)}))}
    return el=>VZ.stackColumns(el,cols,{height:240});
  }
  if(f==='Rank matrix'){const cn=Math.min(7,r.rows.length);return el=>VZ.rankMatrix(el,sh.N.slice(0,6).map(j=>({label:r.cols[j],items:[...r.rows].filter(x=>x[j]!=null).sort((a,b)=>b[j]-a[j]).slice(0,cn).map(x=>({key:String(x[L]).toLowerCase(),name:lab(x[L]),value:sxFmt(r.cols[j],x[j])}))})),{columns:cn,highlight:'near'})}
  if(f==='Bubble chart'){const X=V,Y=sh.N.find(j=>j!==V),Z=sh.N.find(j=>j!==V&&j!==Y),pts=r.rows.filter(x=>x[X]>0&&x[Y]>0),sz=Z!=null?d3.scaleSqrt().domain(d3.extent(pts,x=>x[Z]||0)).range([14,46]):()=>22;return el=>VZ.bubbles(el,{points:pts.map((x,k)=>({x:x[X],y:x[Y],name:lab(x[L]),size:sz(x[Z]||0),color:SX_PAL[k%8],tip:`<b>${sxEsc(x[L])}</b><br>${r.cols[X]} ${sxFmt(r.cols[X],x[X])}<br>${r.cols[Y]} ${sxFmt(r.cols[Y],x[Y])}`})),lines:[],xLabel:r.cols[X],yLabel:r.cols[Y],height:300,fmtX:FV(X),fmtY:FV(Y)})}
  return el=>{el.innerHTML=`<p class="sx-empty">${SX_WHY[f]||'This form needs a different result'}.</p>`};
}
/* The bar: where the question sits, its content state, and one button that names the next step */
function sxPub(){
  const k=sxChecks(),ch=sxChanges(),a=sxA(),pub=a&&isLive(a);
  if(ST.pr){const since=sxChanges(ST.pr.snap).length;return since?{label:'Update pull request',act:'panel',tone:'go'}:{label:'Pending review',act:'panel',tone:'wait'}}
  if(pub&&!ch.length)return{label:'No changes to publish',act:'none',tone:'idle'};
  if(k.blocks)return{label:`Fix ${k.blocks} ${k.blocks===1?'issue':'issues'}`,act:'checks',tone:'fix'};
  return{label:'Open pull request',act:'panel',tone:'go'};
}
function sxPaintBar(){
  const s=subj(ST.sid),a=sxA(),ch=sxChanges(),pub=a&&isLive(a),p=sxPub();
  const st=ST.pr?['pending','In review']:!a?['notyet','Draft']:!isLive(a)?['planned','Planned']:ch.length?['notyet',`${ch.length} unpublished ${ch.length===1?'change':'changes'}`]:['holds','Published'];
  main.querySelector('.sx').style.setProperty('--hue',s.hue);
  $('#sx-bar').innerHTML=`<div class="sx-crumb"><a class="sx-home" href="#studio" title="Studio home, with every question">${SX_CHEV}Studio</a><h1 class="sx-path"><i></i><span class="sx-sn">${s.short}</span><span aria-hidden="true">/</span><b>${sxEsc(ST.q||'New question')}</b></h1></div><div class="sx-stat"><span class="stamp ${st[0]}">${st[1]}</span><span class="sx-pin">Data as of ${fmt.date(LC.asOf)}</span></div><div class="sx-acts">${pub?`<a class="ctl alt" href="#a-${a.id}">Open on its page</a>`:''}${pub&&ch.length&&!ST.pr?'<button class="ctl alt" type="button" id="sx-discard">Discard changes</button>':''}<button class="ctl sx-pubbtn ${p.tone}" type="button" id="sx-pub" data-act="${p.act}"${p.act==='none'?' aria-disabled="true"':''}>${p.label}</button></div>`;
}
/* The card at the top: the queries as tabs on the query step, the charts as tabs on the chart and words steps */
const SX_QI=svg('<ellipse cx="12" cy="6.5" rx="7" ry="2.8"/><path d="M5 6.5v11c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-11"/><path d="M5 12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8"/>',16);
const sxRows=q=>q.stale?'changed, run it again':q.res?`${fmt.int(q.res.rows.length)} rows`:'not run yet';
const SX_BIN=svg('<path d="M5 7h14M10 7V4.5h4V7M7.5 7l.8 12.5h7.4L16.5 7"/>',16);
const SX_PEN=svg('<path d="M4.5 19.5h4l10-10-4-4-10 10z"/><path d="m12.5 7.5 4 4"/>',15);
function sxPaintCharts(){
  const n=ST.charts.length;main.querySelector('.sx')?.classList.toggle('many',n>1);
  /* A rename in progress keeps its text, caret and focus through a repaint */
  const ed=$('#sx-qren-in'),edv=ed?ed.value:null,edf=!!ed&&document.activeElement===ed,eds=ed?[ed.selectionStart,ed.selectionEnd]:null;
  $('#sx-qtabs').innerHTML=ST.queries.map((q,i)=>{const on=i===ST.qcur,k=ST.charts.filter(c=>c.qid===q.id).length,meta=`${sxRows(q).replace(/^\w/,m=>m.toUpperCase())}, ${k?`feeds ${k===1?'one chart':k+' charts'}`:'feeds no chart'}`;
    if(ST.qren===i)return `<span class="sx-chip on editing"><span class="sx-chedit">${SX_QI}<input class="sx-chin" id="sx-qren-in" value="${sxEsc(q.name)}" aria-label="New name for ${sxEsc(q.name)}" aria-describedby="sx-qren-h" autocomplete="off" spellcheck="false"></span><button type="button" class="sx-rn" data-qrenok="${i}" aria-label="Keep the name" data-tip="Keep the name">${SX_TICK}</button><span class="sx-vh" id="sx-qren-h">Letters, digits and underscores. Enter keeps it and Escape leaves it as it was.</span></span>`;
    return `<span class="sx-chip${on?' on':''}${q.stale?' stale':''}"><button type="button" role="tab" aria-selected="${on}" data-qi="${i}">${SX_QI}<span><b class="sx-mono">${sxEsc(q.name)}</b><small>${meta}</small></span></button>${on?`<button type="button" class="sx-rn" data-qren="${i}" aria-label="Rename ${sxEsc(q.name)}" data-tip="Rename">${SX_PEN}</button>`:''}${ST.queries.length>1?`<button type="button" class="sx-rm" data-qrm="${i}" aria-label="Remove ${sxEsc(q.name)}" title="Remove this query">${ICON_X}</button>`:''}</span>`}).join('')+`<button type="button" class="ctl alt" id="sx-addq">${PLUS}Add a query</button>`;
  if(edv!=null){const n=$('#sx-qren-in');if(n){n.value=edv;if(edf){n.focus();n.setSelectionRange(eds[0],eds[1])}}}
  $('#sx-chrow').innerHTML=ST.charts.map((c,i)=>`<span class="sx-chip${i===ST.cur?' on':''}${c.stale?' stale':''}"><button type="button" role="tab" aria-selected="${i===ST.cur}" data-ci="${i}">${glyph(c.form,16)}<span><b>${sxEsc(c.label||c.name||`Chart ${i+1}`)}</b><small>${c.stale?`${sxEsc(sxQName(c.qid))} changed, run it again`:`${sxEsc(c.form)}, from ${sxEsc(sxQName(c.qid))}`}</small></span></button>${n>1?`<button type="button" class="sx-rm" data-rm="${i}" aria-label="Remove ${sxEsc(c.label||c.name)}" title="Remove this chart">${ICON_X}</button>`:''}</span>`).join('')+`<button type="button" class="ctl alt" id="sx-addc">${PLUS}Add a chart</button>`;
  sxPaintSets();
  $('#sx-layrow').innerHTML=`<span class="sx-lab">How the charts sit together</span><span class="sx-seg" role="group" aria-label="How the charts sit together">${Object.keys(SX_LAYS).map(l=>{const off=(l==='One chart')!==(n===1);return `<button type="button" data-lay="${l}" aria-pressed="${l===ST.layout}"${off?` disabled title="${n===1?'Add a second chart first':'Remove charts until one is left'}"`:''}>${l}</button>`}).join('')}</span>${n>1?`<small class="sx-hint">${ST.layout==='Tabs'?'Tabs hide every chart but the first until a reader clicks, so keep them for different views of one answer.':ST.layout==='Side by side'?'Side by side shares one reading and stacks on narrow screens.':'Each chart gets its own reading, the clearest layout for readers.'}</small>`:''}`;
}
/* Renaming a query happens on its tile. Enter, the tick or a click elsewhere keeps the new name; Escape leaves the old one. */
function sxQRenStart(i){
  if(!(i>=0&&i<ST.queries.length))return;
  const moved=ST.qcur!==i;ST.qcur=i;ST.qren=i;sxPaintCharts();if(moved)sxPaintQuery();
  const inp=$('#sx-qren-in');if(inp){inp.focus();inp.select()}
}
function sxQRename(save,refocus){
  const i=ST.qren;if(i==null)return;
  const q=ST.queries[i],inp=$('#sx-qren-in');ST.qren=null;
  if(save&&q&&inp){const nw=sxUniqQ(sxQSlug(inp.value)||q.name,q);if(nw!==q.name){const old=q.name;q.name=nw;toast(`${old} is now ${nw}.`)}}
  sxPaintCharts();sxPaintChart();sxPaintWords();sxPaintFoot();sxPaintChecks();
  if(refocus)$(`#sx-qtabs [data-qi="${i}"]`)?.focus();
}
/* The chart tile's own fields. A field being typed in keeps its text; the rest follow the state. */
function sxPaintSets(){
  const q=sxQ(),c=sxC(),val=(id,v)=>{const e=$(id);if(e&&document.activeElement!==e&&e.value!==v)e.value=v};
  if(!q||!c)return;
  val('#sx-in-cn',c.name);
  const sel=$('#sx-in-cq');if(sel&&document.activeElement!==sel)sel.innerHTML=ST.queries.map(x=>`<option value="${x.id}"${x.id===c.qid?' selected':''}>${sxEsc(x.name)}, ${sxRows(x)}</option>`).join('');
  const qi=ST.queries.findIndex(x=>x.id===c.qid);$('#sx-cgo').innerHTML=qi<0?'':`<button type="button" class="sx-draftb" data-goq="${qi}">Open ${sxEsc(ST.queries[qi].name)}</button>`;
}
/* The column type, and a short profile of what the column holds */
const sxType=(r,i)=>{const v=r.rows.map(x=>x[i]).filter(x=>x!=null);return !v.length?'empty':v.every(x=>typeof x==='number')?'number':v.every(x=>/^\d{4}-\d{2}-\d{2}/.test(String(x)))?'date':'text'};
const sxProf=(r,i,ty)=>{const all=r.rows.map(x=>x[i]),v=all.filter(x=>x!=null),nul=all.length-v.length;let s=ty==='number'?`${fmt.compact(d3.min(v))} to ${fmt.compact(d3.max(v))}`:ty==='date'?`${dm(String(d3.min(v)))} to ${dm(String(d3.max(v)))}`:ty==='text'?`${new Set(v).size} distinct`:'all empty';return nul?`${s}, ${nul} empty`:s};
/* Sorting the rows is for reading them: it changes neither the query nor the chart. Empty values stay last. */
const sxSorted=(r,s)=>!s?r.rows:r.rows.map((x,k)=>[x,k]).sort((a,b)=>{const x=a[0][s.i],y=b[0][s.i];if(x==null||y==null)return x==null&&y==null?a[1]-b[1]:x==null?1:-1;const c=typeof x==='number'&&typeof y==='number'?x-y:String(x).localeCompare(String(y),undefined,{numeric:true});return c?c*s.d:a[1]-b[1]}).map(p=>p[0]);
const sxRowsHtml=rows=>rows.map(x=>`<tr>${x.map(v=>`<td class="${typeof v==='number'?'num':''}">${sxRaw(v)}</td>`).join('')}</tr>`).join('');
function sxGrid(r,n,s){
  const ty=r.cols.map((c,i)=>sxType(r,i)),G={number:'#',date:ICON_DATE,text:'Aa',empty:'·'};
  return `<div class="sx-tw"><table class="t sx-t"><thead><tr>${r.cols.map((c,i)=>{const dir=s&&s.i===i?(s.d>0?'ascending':'descending'):'none';return `<th class="${ty[i]==='number'?'num':''}" scope="col" aria-sort="${dir}"><button type="button" class="sx-sort${dir!=='none'?' on':''}" data-sort="${i}"><span class="sx-ch"><i class="sx-ty ty-${ty[i]}" aria-hidden="true">${G[ty[i]]}</i>${sxEsc(c)}</span>${SX_SORTI[dir]}</button><small>${sxProf(r,i,ty[i])}</small></th>`}).join('')}</tr></thead><tbody>${sxRowsHtml(sxSorted(r,s).slice(0,n))}</tbody></table></div>`;
}
/* A new order redraws only the rows and the headers' marks, so the header keeps its focus */
function sxSortApply(c){
  const tw=$('#sx-res .sx-tw'),r=c.res,s=c.sort;if(!tw||!r)return;
  tw.querySelectorAll('thead th').forEach((th,i)=>{const dir=s&&s.i===i?(s.d>0?'ascending':'descending'):'none',b=th.querySelector('.sx-sort');th.setAttribute('aria-sort',dir);b.classList.toggle('on',dir!=='none');b.lastElementChild.outerHTML=SX_SORTI[dir]});
  tw.querySelector('tbody').innerHTML=sxRowsHtml(sxSorted(r,s).slice(0,Math.min(60,r.rows.length)));tw.scrollTop=0;
}
function sxPaintQuery(){
  const c=sxQ(),ta=$('#sx-sql');if(ta.value!==c.sql)ta.value=c.sql;$('#sx-hl').innerHTML=sxHl(c.sql);
  const r=c.res,box=$('#sx-res');
  sxQueryMeta();sxPaintTables();
  $('#sx-qstate').innerHTML=c.stale?`<span class="sx-state warn">Changed since it ran</span>`:r?`<span class="sx-state ok">${fmt.int(r.rows.length)} rows</span>`:`<span class="sx-state">Not run</span>`;
  box.classList.toggle('stale',!!c.stale);
  const shown=Math.min(60,r?r.rows.length:0),aso=sxAsOf({res:r,enc:{off:[]}});
  box.innerHTML=(c.stale?`<div class="sx-banner" role="status"><span><b>${ST.queries.length>1?sxEsc(c.name):'The query'} has changed since it ran.</b> The rows below, and the charts and values that read it, still come from the last run.</span><button class="ctl" type="button" data-run>Run now</button></div>`:'')+
   (!r?`<p class="sx-empty">${c.runNote||'Run the query to see its rows.'}</p>`:`<div class="sx-strip"><b>${fmt.int(r.rows.length)} rows</b>${r.rows.length>shown?`<span>Showing the first ${shown}</span>`:''}<span>${r.cols.length} columns</span>${aso?`<span>As of ${dm(String(aso))}</span>`:''}<span>${c.ranAt?sxAgo(c.ranAt):'From the published question'}</span></div>${sxGrid(r,shown,c.sort&&c.sort.i<r.cols.length?c.sort:null)}`);
}
/* The header names the tables the query reads; each opens in the table list */
function sxQueryMeta(){
  const c=sxQ(),ts=sxReads(c.sql),unk=sxUnknown(c.sql),btn=t=>`<button type="button" class="sx-tlink" data-tshow="${t}" title="Show its fields">${t}</button>`;
  const list=ts.length?`reads ${sxList([...ts.slice(0,2).map(btn),...(ts.length>2?[`${ts.length-2} more`]:[])])}`:'',bad=unk.length?`<span class="sx-unk">${sxEsc(unk[0])} is not a table in the warehouse</span>`:'';
  const head=list?list[0].toUpperCase()+list.slice(1):'';
  $('#sx-qmeta').innerHTML=[head,bad].filter(Boolean).join('. ');
}
const SX_CHEV=svg('<path d="m9 6 6 6-6 6"/>',14);
const SX_INS=svg('<path d="M5 4.5h6M8 4.5v15M5 19.5h6"/><path d="M17.5 8.5v7M14 12h7"/>',16),SX_SAMPLE=svg('<path d="m8.5 7-5 5 5 5"/><path d="m15.5 7 5 5-5 5"/>',16);
const SX_SORTI={none:svg('<path d="m8 9.5 4-4 4 4M8 14.5l4 4 4-4"/>',13),ascending:svg('<path d="M12 19V5M6.5 10.5 12 5l5.5 5.5"/>',13),descending:svg('<path d="M12 5v14M6.5 13.5 12 19l5.5-5.5"/>',13)};
const SX_CARET=svg('<path d="m7 10 5 5 5-5"/>',15),SX_TICK=svg('<path d="m6.5 12.5 3.6 3.6L17.5 8.6"/>',14);
const SX_HIDEI=svg('<rect x="4" y="5" width="16" height="14" rx="2.5"/><path d="M9.5 5v14"/><path d="m15.5 10-2 2 2 2"/>',17),SX_TABLESI=svg('<rect x="4" y="5" width="16" height="14" rx="2.5"/><path d="M9.5 5v14"/>',16);
/* The four steps. None is locked: each shows its state, and any step is a click away. */
const SX_STEPS=[['query','Query','Query the warehouse'],['chart','Chart','Choose the chart'],['words','Words','Write the words'],['review','Publish','Review and publish']];
function sxStepState(s){
  const cs=ST.charts,many=cs.length>1;
  if(s==='query'){const qs=ST.queries,mq=qs.length>1,stale=qs.filter(q=>q.stale).length,ran=qs.filter(q=>q.res&&!q.stale).length;
    if(stale)return{tone:'warn',text:mq?`${stale} changed since ${stale===1?'it':'they'} ran`:'Changed since it ran'};
    if(ran<qs.length)return{tone:'idle',text:mq?`${ran} of ${qs.length} run`:'Not run yet'};
    return{tone:'ok',text:mq?`${qs.length} queries run`:`${fmt.int(qs[0].res.rows.length)} rows`}}
  if(s==='chart'){const fit=cs.filter(c=>sxFitsC(c,c.form)).length;
    if(cs.some(c=>c.stale))return{tone:'warn',text:'Waiting for a new run'};
    if(fit<cs.length)return{tone:'warn',text:many?`${cs.length-fit} ${cs.length-fit===1?'needs':'need'} a form`:'Pick a form that fits'};
    return{tone:'ok',text:many?`${cs.length} charts, ${ST.layout.toLowerCase()}`:cs[0].form}}
  const k=sxChecks();
  if(s==='words'){const n=[...k.B,...k.W].filter(x=>!x[0]&&/^sx-(w|in-|srcs)/.test(x[3])).length;return n?{tone:'warn',text:`${n} to look at`}:{tone:'ok',text:'Ready'}}
  const a=sxA();
  if(ST.pr)return{tone:'idle',text:sxChanges(ST.pr.snap).length?'New edits to push':'In review'};
  if(k.blocks)return{tone:'block',text:`${k.blocks} to fix`};
  if(a&&isLive(a)&&!sxChanges().length)return{tone:'idle',text:'No changes'};
  return{tone:'ok',text:k.warns?`Ready, ${k.warns} ${k.warns===1?'note':'notes'}`:'Ready'};
}
const sxStateHtml=s=>`<span class="sx-state ${s.tone==='idle'?'':s.tone}">${sxEsc(s.text)}</span>`;
function sxPaintSteps(){
  const el=$('#sx-steps');if(!el)return;
  const had=document.activeElement&&el.contains(document.activeElement)?document.activeElement.dataset.step:null;
  el.innerHTML=`<ol>${SX_STEPS.map(([id,t],i)=>{const s=sxStepState(id);return `<li class="${s.tone}"><button type="button" data-step="${id}"${id===ST.step?' aria-current="step"':''}><i class="sx-si" aria-hidden="true">${s.tone==='ok'?SX_TICK:i+1}</i><span><b><span class="sx-vh">Step ${i+1}: </span>${t}</b><small><span class="sx-vh">, </span>${sxEsc(s.text)}</small></span></button></li>`}).join('')}</ol>`;
  if(had)el.querySelector(`[data-step="${had}"]`)?.focus({preventScroll:true});
}
/* Where each check's fix lives, in words, and the first open check: blocking ones before warnings */
const SX_FIELD={'sx-q':'the query','sx-c':'the chart','sx-w':'the values in the words','sx-in-q':'the question','sx-in-r':'the reading','sx-in-alt':'the text alternative','sx-in-cl':'the chart titles','sx-in-ck':'the key figure','sx-srcs':'the sources'};
const sxFirstIssue=re=>{const k=sxChecks();return [...k.B,...k.W].find(x=>!x[0]&&(!re||re.test(x[3])))||null};
/* Back and Next close every step, and the main button names what comes next */
function sxPaintFoot(){
  const el=$('#sx-foot');if(!el)return;
  const i=SX_STEPS.findIndex(s=>s[0]===ST.step),prev=SX_STEPS[i-1],next=SX_STEPS[i+1],c=sxC(),s=sxStepState(ST.step);
  const back=prev?`<button type="button" class="ctl alt sx-back" data-step="${prev[0]}">${SX_CHEV}${{query:'Back to the query',chart:'Back to the chart',words:'Back to the words'}[prev[0]]}</button>`:'';
  const go=(n,alt)=>`<button type="button" class="ctl${alt?' alt':''}" data-step="${n[0]}">Next: ${n[2].replace(/^\w/,m=>m.toLowerCase())}${SX_CHEV}</button>`;
  let note='',btns='',warn=false,link='',more='';
  if(ST.step==='query'){const q=sxQ(),need=!!q.stale||!q.res,idle=!ST.charts.some(x=>x.qid===q.id),mq=ST.queries.length>1;
    note=q.stale?`${mq?q.name:'The query'} changed since it ran. Run it so the charts and the words use the new rows.`:!q.res?(q.runNote||'Run the query to see its rows.'):idle?`${q.name} returned ${fmt.int(q.res.rows.length)} rows but feeds no chart yet. Point a chart at it under Data from on the Chart step.`:`${fmt.int(q.res.rows.length)} rows are ready${mq?` in ${q.name}`:''}. Next, pick the form that shows them best.`;
    warn=!!q.stale||(idle&&!!q.res);more=idle&&q.res?'<button type="button" class="sx-go" id="sx-qaddc">Or add a chart from it</button>':'';btns=(need?'<button type="button" class="ctl" data-run>Run the query</button>':'')+go(next,need)}
  else if(ST.step==='chart'){note=c.stale?'This chart still shows the last result. Run the query again to redraw it.':!c.res?'The chart appears once the query returns rows.':sxFitsC(c,c.form)?`${c.form} fits the result. Next, write what a reader should take from it.`:'Pick a form that fits the result.';warn=s.tone==='warn';btns=go(next)}
  else if(ST.step==='words'){const first=sxFirstIssue(/^sx-(w|in-|srcs)/);note=first?`${s.text.replace(/^\w/,m=>m.toUpperCase())}. Start with ${SX_FIELD[first[3]]||'the words'}.`:'The words are ready. Next, review the checks and open the pull request.';warn=!!first;link=first?first[3]:'';btns=go(next)}
  else{const p=sxPub(),first=p.act==='checks'?sxFirstIssue():null;note=first?`${s.text.replace(/^\w/,m=>m.toUpperCase())}. Start with ${SX_FIELD[first[3]]||'the first check'}, or see every check above.`:p.act==='none'?'Edit the question first. There is nothing new to publish.':ST.pr?'The pull request shows the reviewer the checks, a preview link and the changes.':'Warnings travel in the pull request for the reviewer.';warn=!!first;
    btns=first?`<button class="ctl" type="button" data-go="${first[3]}">${p.label}</button>`:`<button class="ctl sx-pubgo" type="button" data-act="${p.act}"${p.act==='none'?' aria-disabled="true"':''}>${p.label}</button>`}
  el.innerHTML=`${back}<p class="sx-fnote${warn?' warn':''}">${sxEsc(note)}${link?` <button type="button" class="sx-go" data-go="${link}">Go to it</button>`:''}${more?' '+more:''}</p><span class="sx-fgo">${btns}</span>`;
}
/* Opens a step: its panel shows, the rail and the footer follow, and the focus moves to its heading */
function sxGo(step,{focus=true,scroll=true}={}){
  const root=main.querySelector('.sx');if(!root||!SX_STEPS.some(s=>s[0]===step))return;
  ST.step=step;root.dataset.step=step;sxPaletteClose();
  root.querySelectorAll('[data-pane]').forEach(p=>p.hidden=p.dataset.pane!==step);
  if(step!=='query'&&ST.prevStale)sxPaintPreview();
  sxPaintSteps();sxPaintFoot();
  if(scroll){const head=parseFloat(getComputedStyle(root).getPropertyValue('--head-h'))||58,top=root.getBoundingClientRect().top+scrollY-head;if(scrollY>top+2)scrollTo({top,behavior:'auto'})}
  if(focus)root.querySelector(`[data-pane="${step}"] .sx-step>header h2`)?.focus({preventScroll:true});
}
const sxTy=t=>/^(DATE|TIMESTAMP)/.test(t)?'date':/^(VARCHAR|JSON|TEXT|UUID|BLOB)/.test(t)?'text':/^BOOL/.test(t)?'bool':'number';
const SX_TYG={number:'#',date:ICON_DATE,text:'Aa',bool:'T/F'};
const sxMark=(s,q)=>{const i=q?s.toLowerCase().indexOf(q):-1;return (i<0?sxEsc(s):sxEsc(s.slice(0,i))+`<mark>${sxEsc(s.slice(i,i+q.length))}</mark>`+sxEsc(s.slice(i+q.length))).replace(/_/g,'_<wbr>')};
const sxUsedBy=t=>ANALYSES.filter(a=>isLive(a)&&chartsOf(a).some(c=>(c.table||a.table||'').split(/,\s*/).some(x=>x.replace(/^gold\./,'')===t))).length;
/* The list: the tables the query reads first, then the warehouse's own areas. The find box matches tables, their descriptions and their fields. */
function sxBrowseHtml(q,reads){
  const match=t=>{if(!q)return{ok:true,f:[]};const T=SX_CAT[t],f=T.c.filter(c=>c[0].includes(q)).map(c=>c[0]);return{ok:t.includes(q)||f.length>0||T.d.toLowerCase().includes(q),f}};
  const row=(t,f)=>{const T=SX_CAT[t],inq=reads.includes(t),n=T.c.length;
   return `<li class="sx-trow" data-name="${t}"><button type="button" class="sx-tmain" data-topen="${t}"${T.d?` aria-describedby="sx-td-${t}"`:''}><code>${sxMark(t,q)}</code> ${inq?'<span class="sx-tq">In the query</span> ':''}<small>${n} ${n===1?'field':'fields'}</small></button>${T.d?`<p class="sx-tdesc" id="sx-td-${t}">${sxEsc(sxFirst(T.d))}</p>`:''}<span class="sx-tact"><button type="button" class="sx-ib" data-tins="${t}" aria-label="Insert gold.${t} at the cursor" data-tip="Insert the name at the cursor">${SX_INS}</button><button type="button" class="sx-ib" data-tsam="${t}" aria-label="Sample query on gold.${t}" data-tip="Replace the query with a sample">${SX_SAMPLE}</button><span class="sx-tgo" aria-hidden="true">${SX_CHEV}</span></span>${f.length?`<div class="sx-tmatch"><span>Matching fields</span>${f.slice(0,8).map(n=>`<button type="button" class="sx-fchip" data-fins="${n}" data-ft="${t}">${sxMark(n,q)}</button>`).join('')}${f.length>8?`<span>and ${f.length-8} more</span>`:''}</div>`:''}</li>`};
  const groups=[];
  if(!q&&reads.length)groups.push(['Read by this query',reads.map(t=>[t,[]])]);
  SX_AREAS.forEach(a=>{const ts=Object.keys(SX_CAT).filter(t=>SX_CAT[t].a===a&&(q||!reads.includes(t))).map(t=>[t,match(t)]).filter(([,m])=>m.ok).map(([t,m])=>[t,m.f]);if(ts.length)groups.push([a,ts])});
  const n=groups.reduce((k,[,ts])=>k+ts.length,0);
  return{n,html:`<div class="sx-tscroll" id="sx-tscroll">${groups.length?groups.map(([h,ts])=>`<section class="sx-tg"><h3>${h}<small>${ts.length}</small></h3><ul>${ts.map(([t,f])=>row(t,f)).join('')}</ul></section>`).join(''):`<p class="sx-empty">No table or field matches “${sxEsc(ST.tblQ.trim())}”.</p>`}</div>`};
}
/* One table: what it holds, its shape and sources, and its fields with their types. Fields the query names are marked. */
function sxDetailHtml(t,reads){
  const T=SX_CAT[t],inq=reads.includes(t),q=(ST.tblQ||'').trim().toLowerCase(),words=new Set(sxStripSql(sxQ().sql).toLowerCase().match(/[a-z_][a-z0-9_]*/g)||[]),u=sxUsedBy(t),long=T.d.length>180;
  const prop=(k,v)=>v?`<div><dt>${k}</dt><dd>${v}</dd></div>`:'';
  const typeOf=c=>{const unit=c[2]||c[1].toLowerCase();return `${sxEsc(unit)}${unit.toLowerCase()!==c[1].toLowerCase()?`<small>${sxEsc(c[1])}</small>`:''}`};
  return `<div class="sx-tdet" data-name="${t}"><div class="sx-tdh">
   <div class="sx-tdtop"><button type="button" class="sx-tback" data-tback="">${SX_CHEV}${q?'Back to the results':'All tables'}</button><span class="sx-tdacts"><button type="button" class="sx-ib" data-tins="${t}" aria-label="Insert gold.${t} at the cursor" data-tip="Insert gold.${t} at the cursor">${SX_INS}</button><button type="button" class="sx-ib" data-tsam="${t}" aria-label="Sample query on gold.${t}" data-tip="Replace the query with a sample on gold.${t}">${SX_SAMPLE}</button></span></div>
   <div class="sx-tdt"><h3 tabindex="-1" id="sx-tdh3">${sxMark(t,'')}</h3>${inq?'<span class="sx-tq">In the query</span>':''}</div>
   ${T.d?`<div class="sx-tddw"><p class="sx-tdd${long?' clamp':''}" id="sx-tdd">${sxEsc(T.d)}</p>${long?'<button type="button" class="sx-tmore" data-tmore="" aria-expanded="false" aria-controls="sx-tdd">Show all</button>':''}</div>`:''}
   <dl class="sx-tprops">${prop('Rows',T.n!=null?fmt.int(T.n):'')}${prop('Dates',T.f&&T.l?`${fmt.date(String(T.f).slice(0,10))} to ${fmt.date(String(T.l).slice(0,10))}`:'')}${prop('One row per',T.g.length?sxList(T.g.map(g=>`<code>${sxEsc(g)}</code>`)):'')}${prop('Used by',u?`${u} ${u===1?'question':'questions'}`:'')}${prop('Sources',T.s.length?VZ.sources(T.s):'')}</dl>
   <p class="sx-fhint">Select a field to put it at the cursor, and several in a row to make a list. A bar marks the fields the query reads.</p></div>
   <div class="sx-fwrap" id="sx-fwrap"><div class="sx-fh" aria-hidden="true"><span>Field</span><span>Type</span><span>Description</span><span></span></div><ul class="sx-fl" aria-label="Fields of ${t}">${T.c.map(c=>{const ty=sxTy(c[1]),hit=q&&c[0].includes(q);const used=words.has(c[0]);return `<li class="${[hit?'hit':'',used?'used':''].join(' ').trim()}"><span class="sx-fname"><button type="button" class="sx-fb" data-fins="${c[0]}"><i class="sx-ty ty-${ty}" aria-hidden="true">${SX_TYG[ty]}</i><code>${sxMark(c[0],q)}</code>${used?'<span class="sx-vh">, in the query</span>':''}</button>${T.g.includes(c[0])?'<span class="sx-key">Key</span>':''}</span><span class="sx-fty">${typeOf(c)}</span><span class="sx-fd">${sxEsc(sxFirst(c[3]))}</span><span class="sx-fi" aria-hidden="true">${SX_INS}</span></li>`}).join('')}</ul></div></div>`;
}
/* Draws whichever view is open, keeping its scroll and the focus where they were */
function sxPaintTables(){
  const box=$('#sx-tl');if(!box)return;
  const q=(ST.tblQ||'').trim().toLowerCase(),reads=sxReads(sxQ().sql),sel=ST.tblSel&&SX_CAT[ST.tblSel]?ST.tblSel:null,all=Object.keys(SX_CAT).length;
  ST.readsKey=reads.join();
  const ae=document.activeElement,hold=ae&&box.contains(ae)?[...ae.attributes].find(a=>/^data-(topen|tins|tsam|fins|tback|tmore)$/.test(a.name)):null,ft=hold&&ae.dataset.ft,sc=$('#sx-tscroll')||$('#sx-fwrap'),top=sc?sc.scrollTop:0,same=box.dataset.view===(sel||'');
  let count;
  if(sel){box.innerHTML=sxDetailHtml(sel,reads);count=`${SX_CAT[sel].c.length} fields`}
  else{const b=sxBrowseHtml(q,reads);box.innerHTML=b.html;count=q?`${b.n} of ${all} tables`:`${all} tables`}
  box.dataset.view=sel||'';
  const live=$('#sx-tcount');if(live&&live.textContent!==count)live.textContent=count;
  const sc2=$('#sx-tscroll')||$('#sx-fwrap');if(sc2&&same)sc2.scrollTop=top;
  if(hold){const el=box.querySelector(`[${hold.name}="${hold.value}"]${ft?`[data-ft="${ft}"]`:''}`);if(el)el.focus({preventScroll:true})}
}
function sxOpenTable(t){
  ST.tblTop=($('#sx-tscroll')||{}).scrollTop||0;ST.tblSel=t;sxPaintTables();
  const w=$('#sx-fwrap'),hit=w&&w.querySelector('li.hit');if(hit){const fh=w.querySelector('.sx-fh');w.scrollTop=Math.max(0,hit.offsetTop-(fh&&fh.offsetParent?fh.offsetHeight:0)-2)}
  $('#sx-tdh3')?.focus({preventScroll:true});
}
function sxCloseTable(){
  const t=ST.tblSel;ST.tblSel=null;sxPaintTables();
  const sc=$('#sx-tscroll');if(sc)sc.scrollTop=ST.tblTop||0;
  const b=$(`#sx-tl [data-topen="${t}"]`);if(b){b.focus({preventScroll:true});const r=b.closest('.sx-trow'),y=r.offsetTop;if(sc&&(y<sc.scrollTop+30||y>sc.scrollTop+sc.clientHeight-40))sc.scrollTop=Math.max(0,y-60)}
}
/* From a table's name in the editor's header: the table, open */
function sxShowTable(t){
  if(ST.step!=='query')sxGo('query',{focus:false});
  ST.tblOpen=true;$('#sx-qgrid')?.classList.remove('closed');
  const d=$('#sx-tables');sxOpenTable(t);
  const r=d.getBoundingClientRect();if(r.top<70||r.top>innerHeight-120)d.scrollIntoView({block:'start',behavior:LCC.reduce()?'auto':'smooth'});
}
/* Credits: the sources the query's fields come from, then the rest. A note says when the picks differ from what the query reads. */
function sxPaintSources(){
  sxSyncSrc();
  const own=sxOwner(),act=sxActualOf(own),auto=sxAuto(own),pick=own.src,q=[...act.keys()],g=sxSrcGap(own),vary=sxReads(own===ST?ST.charts.map(c=>c.sql).join(' '):own.sql).some(t=>SX_CAT[t].v);
  const all=[...new Set([...q,...sxSources(),...pick])].filter(id=>VZ.sourceInfo(id)),rest=all.filter(id=>!act.has(id));
  const why=v=>`${v.sure?'Read by the query':'May be read by the query, as the catalog does not say which source this field comes from'}: ${sxEsc(v.w.slice(0,3).join('; '))}${v.w.length>3?`, and ${v.w.length-3} more`:''}`;
  const chip=id=>{const s=VZ.sourceInfo(id),on=pick.includes(id),v=act.get(id);return `<button type="button" class="sx-src${v&&v.sure&&!on?' miss':''}${v&&!v.sure?' maybe':''}" data-src="${id}" aria-pressed="${on}"${v?` title="${why(v)}"`:''}><img src="${s.logo}" alt="" width="20" height="20" loading="lazy">${s.name}${v&&!v.sure?'<small>possibly</small>':''}</button>`};
  $('#sx-srcs').innerHTML=q.length?`<div class="sx-srow"><span class="sx-sk">Read by the query</span><div class="sx-srcs">${q.map(chip).join('')}</div></div><div class="sx-srow"><span class="sx-sk">Not read by it</span><div class="sx-srcs">${rest.map(chip).join('')}</div></div>`:`<div class="sx-srcs">${all.map(chip).join('')}</div>`;
  const names=ids=>sxList(ids.map(id=>VZ.sourceInfo(id).name)),is=ids=>ids.length===1?'is':'are';
  const note=!q.length?'The query reads no table in the warehouse yet, so pick its sources by hand.'
   :auto?`Picked from the fields the query reads, and kept in step as the query changes.${vary?' Its table holds rows from many sources, so keep only those its rows come from.':''} Pick one yourself to choose by hand.`
   :g.same?'Picked by hand, and they match the fields the query reads.'
   :`Picked by hand. ${g.miss.length?`${names(g.miss)} ${is(g.miss)} read by the query but not credited. `:''}${g.maybe.length?`${names(g.maybe)} may be read by it and ${g.maybe.length===1?'is':'are'} not credited. `:''}${g.extra.length?`${names(g.extra)} ${is(g.extra)} credited but not read by it.`:''}`;
  const n=$('#sx-srcnote');n.classList.toggle('warn',!g.ok&&!auto);n.innerHTML=`${!g.ok&&!auto?ICON_WARN:''}<span>${note.trim()}</span>${!auto&&!g.same?'<button type="button" class="sx-draftb" id="sx-srcauto">Use the query’s sources</button>':''}`;
}
function sxPaintChart(){
  const c=sxC(),r=sxEff(c),sug=sxSuggestC(c),tile=(f,why)=>{const ok=!why;return `<button type="button" class="sx-form" role="radio" aria-checked="${f===c.form}" data-form="${f}"${ok?'':' aria-disabled="true"'}>${glyph(f,20)}<span>${f}</span>${ok?(f===sug?'<small>Suggested</small>':c.live&&f===c.own?'<small>Current</small>':''):`<small class="why">${why}</small>`}</button>`};
  const fitsLast=f=>{if(c.live&&c.own===f&&!c.enc.off.length)return true;const sh=sxShape(sxEff(c));return !!(sh&&SX_RULE[f]&&SX_RULE[f](sh))},fit=SX_FORMS.filter(f=>c.stale?fitsLast(f):sxFitsC(c,f)),custom=SX_GROUPS[2][1],no=SX_FORMS.filter(f=>!fit.includes(f)&&!custom.includes(f));
  if(c.own&&!SX_FORMS.includes(c.own)&&!fit.includes(c.own))fit.unshift(c.own);
  $('#sx-cstate').innerHTML=c.stale?`<span class="sx-state warn">Waiting for the new result</span>`:sxFitsC(c,c.form)?`<span class="sx-state ok">${sxEsc(c.form)} fits</span>`:`<span class="sx-state warn">Pick a form that fits</span>`;
  $('#sx-forms').innerHTML=`<div class="sx-fg"><span class="sx-lab">${c.stale?'Fits the last result':'Fits this result'} <small>${fit.length}</small></span><div class="sx-fgrid">${fit.map(f=>tile(f)).join('')||'<p class="sx-empty">Run the query to see which forms fit. <button type="button" class="sx-go" data-step="query">Go to the query</button></p>'}</div></div>
   <details class="sx-fg sx-more"><summary><span class="sx-lab">Needs different data <small>${no.length+custom.length}</small></span></summary><div class="sx-fgrid">${no.map(f=>tile(f,SX_WHY[f]||'Needs a different result')).join('')}${custom.filter(f=>f!==c.own).map(f=>tile(f,'Built in code for one question')).join('')}</div></details>`;
  const desc=!r?'':r.kind==='time'?`a date and ${r.spec.series.length===1?'one number':r.spec.series.length+' numbers'}`:'labels and numbers';
  $('#sx-cmeta').textContent=!r?`Run ${sxQName(c.qid)} first`:`${sxQName(c.qid)} returns ${desc}`;
  /* Named slots: the columns the chart reads, each one switchable */
  const R=c.res;let slots='';
  if(R&&R.kind==='time'){slots=`<span class="sx-field"><small>Across</small><b>${ICON_DATE} ${sxEsc(R.cols[0])}</b></span><span class="sx-field"><small>Values, select to hide or show</small><span class="sx-vals">${R.spec.series.map((s,i)=>{const on=!c.enc.off.includes(i);return `<button type="button" class="sx-val" data-val="${i}" aria-pressed="${on}"><i style="background:${s.color||(i?SX_PAL[i%8]:subj(ST.sid).hue)}"></i>${sxEsc(R.cols[i+1]||s.name)}</button>`}).join('')}</span></span>`}
  else if(R){const sh=sxShape(R),{L,V}=sxLV(c,R),ids=R.cols.map((cn,i)=>i).filter(i=>/(^|_)(id|rank)$/i.test(R.cols[i])&&sxType(R,i)==='number'),cut=sxTop(R,L,V,c.enc.top).cut;
    slots=`<label class="sx-field"><small>Labels</small><select data-enc="label">${sh.T.map(i=>`<option value="${i}"${i===L?' selected':''}>${sxEsc(R.cols[i])}</option>`).join('')}</select></label><label class="sx-field"><small>Value</small><select data-enc="value">${sh.N.map(i=>`<option value="${i}"${i===V?' selected':''}>${sxEsc(R.cols[i])}</option>`).join('')}</select></label><label class="sx-field"><small>Show the top</small><select data-enc="top">${[5,10,15,0].map(n=>`<option value="${n}"${n===c.enc.top?' selected':''}>${n||'All'}</option>`).join('')}</select></label>${cut&&/Ranked|Treemap|Flow|Stacked col/.test(c.form)?`<small class="sx-note2">Showing the top ${c.enc.top} of ${c.enc.top+cut} ${sxEsc(R.cols[L])} values. The other ${cut} are summed as Other.</small>`:''}${ids.length?`<small class="sx-note2">${sxEsc(R.cols[ids[0]])} looks like an identifier, so it is not offered as a value.</small>`:''}`}
  $('#sx-fields').innerHTML=`${slots}${R&&R.kind==='time'&&/Line|Area|Step/.test(c.form)?`<label class="sx-ck"><input type="checkbox" id="sx-ends"${c.ends?' checked':''}> Label the line ends</label>`:''}<span class="sx-cacts"><button type="button" class="ctl alt" id="sx-choose">Choose for me</button>${c.live?'<button type="button" class="ctl alt" id="sx-reset">Reset chart</button>':''}</span>`;
}
function sxPaintWords(){
  const set=(id,v)=>{const e=$(id);if(e&&e.value!==v)e.value=v},c=sxC(),own=sxOwner(),many=sxMany(),per=sxPer(),n=ST.cur+1,ci=per?ST.cur:0;
  set('#sx-in-q',ST.q);set('#sx-in-f',ST.f);set('#sx-in-av',ST.av);set('#sx-in-al',ST.al);
  $('#sx-cw').hidden=!many;$('#sx-cw-h').textContent=`Chart ${n}`;set('#sx-in-cl',c.label);set('#sx-in-ck',c.key);
  set('#sx-in-r',own.read);$('#sx-rl').textContent=per?`Reading under chart ${n}`:many?'Reading under the charts':'Reading under the chart';
  set('#sx-in-alt',c.alt);$('#sx-altl').textContent=many?`Text alternative for chart ${n}`:'Text alternative for the chart';
  $('#sx-sl').textContent=per?`Sources credited under chart ${n}`:many?'Sources credited under the charts':'Sources credited under the chart';
  const T=sxTokensOf(c),pre=many?`${c.name}.`:'';
  $('#sx-tok').innerHTML=Object.keys(T).length?`<span class="sx-lab">Values from ${many?`chart ${n}, named ${sxEsc(c.name)}`:'the result'}. Select one, or type {{ in any field.</span>${Object.entries(T).filter(([k])=>!SX_HIDE.includes(k)).map(([k,[v,l]])=>`<button type="button" class="sx-tok" data-tok="${pre}${k}" title="Places {{${pre}${k}}}"><span>${l}</span><b>${sxEsc(v)}</b></button>`).join('')}`:`<span class="sx-lab">Run ${sxEsc(sxQName(c.qid))}, the query this chart reads, to pick values from its result.</span>`;
  sxReadsAs();
  $('#sx-wstate').innerHTML=sxStateHtml(sxStepState('words'));
  sxPaintSources();
  $('#sx-sugg').innerHTML=ST.sugg?`<div class="sx-sugg" role="region" aria-label="Suggested ${ST.sugg.field==='read'?'reading':'text alternative'}"><span class="sx-lab">Drafted from the result, with values only. Use it as a start.</span><p>${sxFillHtml(ST.sugg.text,ci)}</p><div><button type="button" class="ctl" id="sx-sugg-ok">Use this draft</button><button type="button" class="ctl alt" id="sx-sugg-no">Dismiss</button></div></div>`:'';
}
/* Under each field, the sentence as a reader will see it */
function sxReadsAs(){
  const per=sxPer(),c=sxC(),ci=per?ST.cur:0,line=(id,t,i)=>{const e=$(id);if(e)e.innerHTML=t&&SX_TOK.test(t)?`Reads as: ${sxFillHtml(t,i)}`:'';SX_TOK.lastIndex=0};
  line('#sx-ra-f',ST.f,0);line('#sx-ra-av',[ST.av,ST.al].filter(Boolean).join(' '),0);line('#sx-ra-ck',c.key,ST.cur);line('#sx-ra-r',sxOwner().read,ci);line('#sx-ra-alt',c.alt,ST.cur);
  const o=sxOwner(),n=(sxFill(o.read,ci).match(/\S+/g)||[]).length,e=$('#sx-rc');if(e)e.textContent=`${n} ${n===1?'word':'words'}, aim for 15 to 70`;
}
/* The whole question, in its layout, drawn by the same code as the page */
function sxPaintPreview(){
  sxSyncSrc();
  /* The query step has no preview, so it is drawn when a step that shows it opens, at its real size */
  if(ST.step==='query'){ST.prevStale=true;return}
  ST.prevStale=false;
  ST.handles.forEach(h=>h&&h.destroy&&h.destroy());ST.handles=[];
  const live=inSubject(ST.sid).filter(isLive),a=sxA(),idx=a&&isLive(a)?live.indexOf(a):live.length,s=subj(ST.sid),many=sxMany(),lay=SX_LAYS[ST.layout];
  const d={id:'sx-draft',subject:ST.sid,form:ST.charts[0].form,q:sxEsc(ST.q||'Your question'),f:sxFillHtml(ST.f,0)||'Your finding becomes the headline',table:'',sql:ST.charts.map(c=>c.sql).join('\n\n')};
  if(many){d.layout=lay;d.charts=ST.charts.map((c,i)=>({id:'c'+i,label:sxEsc(c.label||`Chart ${i+1}`),key:sxFillHtml(c.key,i),form:c.form,table:'',sql:c.sql,read:sxFillHtml(c.read,i),src:c.src}));d.read=sxFillHtml(ST.read,0);d.src=lay==='pair'?ST.src:[...new Set(ST.charts.flatMap(c=>c.src))];chartSel['sx-draft']='c'+ST.cur}
  else{d.read=sxFillHtml(ST.charts[0].read,0);d.src=ST.charts[0].src}
  const card=$('#sx-card');card.classList.toggle('phone',ST.device==='phone');
  card.innerHTML=(ST.charts.some(c=>c.stale)?'<p class="sx-ribbon" role="status">Some charts and values here come from results that are out of date. Run their queries to refresh them.</p>':'')+article(d,idx,[d,d]);
  card.querySelectorAll('[data-view]').forEach(el=>{const i=el.dataset.c?+el.dataset.c.slice(1):0,c=ST.charts[i];if(c.alt)el.setAttribute('aria-label',sxFill(c.alt,i));el.setAttribute('role','img');const h=sxViewFor(i)(el);if(h)ST.handles.push(h)});
  $('#sx-deck').innerHTML=`<div class="qdeck sx-deck"><div class="qcard" style="--hue:${s.hue}"><span class="qcard-top"><span class="qno">${idx+1}</span><span class="qr">${many?`<small>${ST.charts.length} charts</small>`:''}${glyph(ST.charts[0].form)}</span></span><h3>${sxEsc(ST.q||'Your question')}</h3><span class="ans">${sxFillHtml(ST.av,0)}</span><small>${sxFillHtml(ST.al,0)}</small></div></div>`;
}
function sxPaintChecks(){
  const k=sxChecks(),row=([ok,t,m,go],sev)=>`<li class="${ok?'ok':sev}">${ok?ICON_OK:sev==='block'?ICON_BLOCK:ICON_WARN}<span>${t}${!ok&&go?` <button type="button" class="sx-go" data-go="${go}">Go to it</button>`:''}</span><small>${sxEsc(String(m))}</small></li>`;
  $('#sx-checks').innerHTML=`<li class="sx-tier"><b>Must pass</b><small>${k.blocks?`${k.blocks} to fix`:'All pass'}</small></li>${k.B.map(x=>row(x,'block')).join('')}<li class="sx-tier"><b>Worth a look</b><small>${k.warns?`${k.warns} open, listed in the pull request`:'All clear'}</small></li>${k.W.map(x=>row(x,'warn')).join('')}`;
  const ch=ST.pr?sxChanges(ST.pr.snap):sxChanges(),cl=$('#sx-changes');
  if(cl){$('#sx-chg-h').textContent=ST.pr?'Changes since the pull request opened':'What changes';cl.innerHTML=(ch.length?ch:[['','No changes yet']]).map(([m,t])=>`<li>${m?`<i class="sx-m m-${m}">${m}</i>`:''}<span>${sxEsc(t)}</span></li>`).join('')}
  const rs=$('#sx-rstate');if(rs)rs.innerHTML=sxStateHtml(sxStepState('review'));
  sxPaintBar();sxPaintSteps();sxPaintFoot();
}
/* The pull request, as a reviewer will read it: branch, files, changes in plain words, checks and warnings */
function sxOpenPanel(){
  const a=sxA(),slug=String(ST.q||'new question').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,48),stem=`analyses/${ST.sid}/${a?a.id:slug}`,used=ST.queries.filter(q=>ST.charts.some(c=>c.qid===q.id)),bq=ST.base?(ST.base.queries||[]):[],files=[[a&&isLive(a)?'M':'A',`${stem}.yml`],...used.map(q=>{const o=bq.find(x=>x.id===q.id);return[!o?'A':o.sql!==q.sql||o.name!==q.name?'M':'',`${stem}--${q.name}.sql`]}).filter(f=>f[0]),...bq.filter(o=>!used.some(q=>q.id===o.id)).map(o=>['D',`${stem}--${o.name}.sql`])];
  const k=sxChecks(),ch=ST.pr?sxChanges(ST.pr.snap):sxChanges(),warns=k.W.filter(x=>!x[0]);
  const dlg=document.createElement('div');dlg.className='sx-dlg';dlg.innerHTML=`<div class="sx-dlg-box" role="dialog" aria-modal="true" aria-labelledby="sx-dlg-h"><header><h2 id="sx-dlg-h">${ST.pr?'Pull request':'Open a pull request'}</h2><button type="button" class="sx-rm" data-close aria-label="Close">${ICON_X}</button></header>
   ${ST.pr?`<p class="sx-prstate"><span class="stamp pending">${sxChanges(ST.pr.snap).length?'Has new edits since it opened':'Pending review'}</span> On branch <code>${sxEsc(ST.pr.branch)}</code>. A reviewer sees the checks, the preview link and the changes below.</p>`:`<label class="sx-field"><small>Branch</small><input id="sx-br" value="studio/${ST.sid}-${slug.slice(0,40)}"></label>`}
   <div class="sx-dsec"><span class="sx-lab">Files</span><ul class="sx-files">${files.map(([m,f])=>`<li><i class="sx-m m-${m}">${m}</i><code>${sxEsc(f)}</code></li>`).join('')}</ul></div>
   <div class="sx-dsec"><span class="sx-lab">${ST.pr?'Changes since it opened':'Changes, in plain words'}</span><ul class="sx-files">${(ch.length?ch:[['','No changes']]).map(([m,t])=>`<li>${m?`<i class="sx-m m-${m}">${m}</i>`:''}<span>${sxEsc(t)}</span></li>`).join('')}</ul></div>
   <div class="sx-dsec"><span class="sx-lab">Checks</span><p class="sx-dnote">${k.B.length-k.blocks} of ${k.B.length} must-pass checks pass.${warns.length?` ${warns.length} ${warns.length===1?'warning goes':'warnings go'} into the description: ${warns.map(w=>sxEsc(w[1].toLowerCase())).join('; ')}.`:' No warnings.'}</p></div>
   ${ST.pr?'':`<label class="sx-field"><small>Description</small><textarea id="sx-msg" rows="3">${sxEsc((a&&isLive(a)?`Edit ${subj(ST.sid).short}: `:`Add to ${subj(ST.sid).short}: `)+(ST.q||'New question'))}</textarea></label>`}
   <p class="sx-dnote">The site builds on the pull request and posts a preview link. Merging publishes it; if a build fails, the last good version stays live. This preview of the Studio does not contact GitHub.</p>
   <footer><button type="button" class="ctl alt" data-close>${ST.pr?'Close':'Cancel'}</button>${ST.pr?(sxChanges(ST.pr.snap).length?'<button type="button" class="ctl" data-prup>Push the new edits</button>':''):'<button type="button" class="ctl" data-propen>Open pull request</button>'}</footer></div>`;
  const back=document.activeElement;document.body.append(dlg);
  const close=()=>{dlg.remove();(back&&back.focus)&&back.focus()};
  dlg.addEventListener('click',e=>{if(e.target===dlg||e.target.closest('[data-close]')){close();return}
    if(e.target.closest('[data-propen]')){ST.pr={branch:$('#sx-br').value||'studio/draft',snap:sxSnap(),at:Date.now()};close();sxPaint();toast('Pull request opened in this preview. In a full build, GitHub runs the site build on it and posts a preview link.');return}
    if(e.target.closest('[data-prup]')){ST.pr.snap=sxSnap();close();sxPaint();toast('The new edits are pushed to the pull request. A reviewer is asked to look again.')}});
  dlg.addEventListener('keydown',e=>{if(e.key==='Escape')close();if(e.key==='Tab'){const f=[...dlg.querySelectorAll('button,input,textarea,[href]')].filter(x=>!x.disabled);if(!f.length)return;const i=f.indexOf(document.activeElement);if(e.shiftKey&&i<=0){e.preventDefault();f[f.length-1].focus()}else if(!e.shiftKey&&i===f.length-1){e.preventDefault();f[0].focus()}}});
  (dlg.querySelector('input,textarea')||dlg.querySelector('[data-close]')).focus();
}
/* The {{ palette: every value with its current figure, opened while typing */
function sxPalette(el){
  sxPaletteClose();const many=sxMany(),items=[];
  ST.charts.forEach((c,i)=>{const T=sxTokensOf(c);Object.entries(T).filter(([k])=>!SX_HIDE.includes(k)).forEach(([k,[v,l]])=>items.push({tok:many?`${c.name}.${k}`:k,v,l,chart:many?(c.label||c.name):''}))});
  if(!items.length)return;
  const box=document.createElement('div');box.className='sx-pal';box.setAttribute('role','listbox');box.id='sx-pal';
  box.innerHTML=items.map((it,i)=>`<button type="button" role="option" data-pi="${i}" aria-selected="${i===0}"><code>{{${sxEsc(it.tok)}}}</code><span>${sxEsc(it.l)}${it.chart?`, ${sxEsc(it.chart)}`:''}</span><b>${sxEsc(it.v)}</b></button>`).join('');
  const r=el.getBoundingClientRect();document.body.append(box);const W=document.documentElement.clientWidth,bw=box.offsetWidth,bh=box.offsetHeight;box.style.left=Math.max(8,Math.min(W-bw-8,r.left))+'px';box.style.top=(r.bottom+4+bh>innerHeight&&r.top-4-bh>8?r.top-4-bh:r.bottom+4)+'px';
  ST.pal={el,items,on:0,box};
  box.addEventListener('mousedown',e=>e.preventDefault());
  box.addEventListener('click',e=>{const b=e.target.closest('[data-pi]');if(b)sxPalettePick(+b.dataset.pi)});
}
function sxPalettePick(i){const p=ST.pal;if(!p)return;const el=p.el,it=p.items[i],at=el.selectionStart,before=el.value.slice(0,at).replace(/\{\{[a-z0-9_.]*$/i,'');el.value=before+`{{${it.tok}}}`+el.value.slice(at);const pos=before.length+it.tok.length+4;el.focus();el.setSelectionRange(pos,pos);sxPaletteClose();el.dispatchEvent(new Event('input',{bubbles:true}))}
function sxPaletteClose(){if(ST.pal){ST.pal.box.remove();ST.pal=null}}
/* Tooltips for icon buttons: shown on hover, and on focus from the keyboard */
function sxTips(root){
  const tipShow=el=>{let tip=$('.sx-tip');if(!tip){tip=document.createElement('div');tip.className='sx-tip';tip.setAttribute('role','tooltip');document.body.append(tip)}tip.textContent=el.dataset.tip;tip.hidden=false;const r=el.getBoundingClientRect(),w=tip.offsetWidth,h=tip.offsetHeight;tip.style.left=Math.max(8,Math.min(document.documentElement.clientWidth-w-8,r.left+r.width/2-w/2))+'px';tip.style.top=(r.top-h-8>8?r.top-h-8:r.bottom+8)+'px'};
  const tipHide=()=>{const t=$('.sx-tip');if(t)t.hidden=true};
  root.addEventListener('pointerover',e=>{const el=e.target.closest('[data-tip]');if(el)tipShow(el)});
  root.addEventListener('pointerout',e=>{const el=e.target.closest('[data-tip]');if(el&&!el.contains(e.relatedTarget))tipHide()});
  root.addEventListener('focusin',e=>{const el=e.target.closest&&e.target.closest('[data-tip]');if(el&&el.matches(':focus-visible'))tipShow(el);else tipHide()});
  root.addEventListener('focusout',tipHide);root.addEventListener('scroll',tipHide,true);root.addEventListener('pointerdown',tipHide);
}
function sxPaint(){sxPaintCharts();sxPaintQuery();sxPaintChart();sxPaintWords();sxPaintPreview();sxPaintChecks()}
let sxT=0;const sxSoon=f=>{clearTimeout(sxT);sxT=setTimeout(f,200)};

/* The Studio's two pages, added to the site's views */
Object.assign(V,{
 /* Studio home: every question by section, the work in progress, and a new question in any section */
 studio(){
  sxStash();
  const wip=[...ST.work.entries()].map(([key,o])=>({key,...o.sum})).sort((a,b)=>b.at-a.at),news=wip.filter(w=>w.isNew);
  const pubN=ANALYSES.filter(isLive).length,planN=ANALYSES.length-pubN,sumOf=id=>(ST.work.get(id)||{}).sum;
  const stampOf=a=>{const w=sumOf(a.id);return w&&w.pr?['pending','In review']:w&&w.n?['notyet',`${w.n} unpublished ${w.n===1?'change':'changes'}`]:w&&w.planned?['notyet','Being written']:isLive(a)?['holds','Published']:['planned','Planned']};
  const FL={all:'All',live:'Published',planned:'Planned',wip:'In progress'},SAY={ok:'ready',warn:'needs a look',block:'blocked',idle:'not started'};
  main.innerHTML=`<div class="sh-root"><section class="night"><div class="wrap s-hero">
    <p class="crumb"><a href="#overview">Overview</a></p>
    <h1>Studio</h1>
    <p>Build a question for the site in four steps: query the warehouse, choose a chart, write the words, publish. Pick one to edit, or start a new one in any section.</p>
    <div class="sh-new"><span class="sh-newl" id="sh-newl">${PLUS}New question in</span><div class="sh-secs" role="group" aria-labelledby="sh-newl">${SUBJECTS.map(s=>`<button type="button" class="sh-chip" data-new="${s.id}" style="--hue:${s.hue}"><i></i>${s.short}</button>`).join('')}</div></div>
    <dl class="kp"><div><dt>Published</dt><dd>${pubN}</dd></div><div><dt>Planned</dt><dd>${planN}</dd></div><div><dt>In progress</dt><dd>${wip.length}</dd></div><div><dt>Data through</dt><dd>${fmt.date(LC.asOf)}</dd></div></dl>
  </div></section>
  <div class="sheet"><div class="wrap" style="padding-bottom:64px">
    <div id="sh-wip"></div>
    <div class="sec-head sh-head"><h2>Every question</h2><div class="sh-tools"><span class="sx-findw">${SX_FIND}<input class="sx-find" id="sh-find" type="search" placeholder="Find a question" aria-label="Find a question" autocomplete="off" value="${sxEsc(ST.homeQ||'')}"></span><span class="chips" id="sh-chips" role="group" aria-label="Show"></span></div></div>
    <p class="sx-vh" id="sh-count" aria-live="polite"></p>
    <div class="sh-grid" id="sh-grid"></div>
  </div></div></div>`;
  $('#sh-wip').innerHTML=!wip.length?'':`<div class="sec-head"><h2>Carry on</h2><span>${wip.length===1?'One question has':wip.length+' questions have'} work that is not published yet</span></div><div class="sh-wips">${wip.map(w=>{const s=subj(w.sid),st=w.pr?['pending','In review']:w.isNew?['notyet','New, not published']:w.planned?['notyet','Being written']:['notyet',`${w.n} unpublished ${w.n===1?'change':'changes'}`];
    return `<article class="card sh-w" style="--hue:${s.hue}"><p class="sh-wt"><span class="sh-sub"><i></i>${s.short}</span><span class="stamp ${st[0]}">${st[1]}</span></p><h3>${sxEsc(w.q||'New question')}</h3><ol class="sh-steps" aria-label="Steps">${SX_STEPS.map((x,i)=>`<li class="${w.states[i]}">${x[1]}<span class="sx-vh">, ${SAY[w.states[i]]}</span></li>`).join('')}</ol><p class="sh-wa"><button type="button" class="ctl" data-key="${w.key}">Continue${SX_CHEV}</button><button type="button" class="sx-ib" data-drop="${w.key}" aria-label="Discard the unpublished work on ${sxEsc(w.q||'the new question')}" data-tip="${w.isNew?'Discard this draft':'Discard this work'}">${SX_BIN}</button></p></article>`}).join('')}</div>`;
  const paintChips=()=>{const f=ST.homeF||'all';$('#sh-chips').innerHTML=Object.entries(FL).map(([k,n])=>`<button type="button" class="chip" data-hf="${k}" aria-pressed="${k===f}">${n}</button>`).join('')};
  const paintGrid=()=>{
    const q=(ST.homeQ||'').trim().toLowerCase(),f=ST.homeF||'all',hit=t=>!q||String(t||'').toLowerCase().includes(q);let shown=0;
    const cards=SUBJECTS.map(s=>{
      const all=inSubject(s.id),live=all.filter(isLive).length;
      const rows=all.filter(a=>(f==='all'||(f==='live'&&isLive(a))||(f==='planned'&&!isLive(a))||(f==='wip'&&!!sumOf(a.id)))&&(hit(a.q)||hit(a.f)));
      const drafts=news.filter(w=>w.sid===s.id&&(f==='all'||f==='wip')&&hit(w.q));
      if(!rows.length&&!drafts.length&&(q||f!=='all'))return'';
      shown+=rows.length+drafts.length;
      const row=(attr,t,st,meta)=>`<li><button type="button" class="sh-q" ${attr}><span class="t">${t}</span><span class="m"><span class="stamp ${st[0]}">${st[1]}</span>${meta}</span><span class="go" aria-hidden="true">${SX_CHEV}</span></button></li>`;
      return `<section class="card sh-sec" style="--hue:${s.hue}" aria-labelledby="sh-h-${s.id}"><header><h3 id="sh-h-${s.id}"><i></i>${s.name}</h3><small>${live} published${all.length-live?`, ${all.length-live} planned`:''}</small></header><ul class="sh-rows">${rows.map(a=>{const cs=chartsOf(a),forms=[...new Set(cs.map(c=>c.form))];return row(`data-aid="${a.id}"`,a.q,stampOf(a),`<span class="sh-forms">${forms.slice(0,3).map(x=>glyph(x,14)).join('')}${cs.length>1?`${cs.length} charts`:sxEsc(forms[0]||'')}</span>`)}).join('')}${drafts.map(w=>row(`data-key="${w.key}"`,sxEsc(w.q||'New question'),['notyet','New, not published'],'')).join('')}</ul><button type="button" class="sh-add" data-new="${s.id}">${PLUS}New question in ${s.short}</button></section>`}).filter(Boolean);
    $('#sh-grid').innerHTML=cards.join('')||`<p class="sx-empty">No ${f==='all'?'':FL[f].toLowerCase()+' '}question matches${q?` “${sxEsc(ST.homeQ.trim())}”`:' that filter'}.</p>`;
    $('#sh-count').textContent=q||f!=='all'?`${shown} ${shown===1?'question':'questions'} shown`:'';
  };
  paintChips();paintGrid();
  const root=main.querySelector('.sh-root');
  root.addEventListener('click',e=>{
    const b=e.target.closest('button');if(!b)return;
    if(b.dataset.aid){sxOpenQ(b.dataset.aid);location.hash='studio-edit';return}
    if(b.dataset.new){sxNewQ(b.dataset.new);location.hash='studio-edit';toast(`New question in ${subj(b.dataset.new).short}. It starts from a sample query on a table the section already uses.`);return}
    if(b.dataset.key){sxResume(b.dataset.key);location.hash='studio-edit';return}
    if(b.dataset.drop){const k=b.dataset.drop,w=ST.work.get(k);if(w&&confirm(`Discard the unpublished work on “${w.sum.q||'the new question'}”?`)){ST.work.delete(k);if(ST.key===k)ST.key=null;V.studio();toast('That work is discarded.')}return}
    if(b.dataset.hf){ST.homeF=b.dataset.hf;paintChips();paintGrid();$(`#sh-chips [data-hf="${ST.homeF}"]`)?.focus()}
  });
  root.addEventListener('input',e=>{if(e.target.id==='sh-find'){ST.homeQ=e.target.value;paintGrid()}});
  sxTips(root);
  cleanup.push(()=>{document.querySelector('.sx-tip')?.remove()});
 },
 /* The editor, for the question chosen on the home page */
 studioEdit(){
  if(!ST.key){try{history.replaceState(null,'','#studio')}catch(e){}V.studio();return}
  if(!ST.step)ST.step='query';
  if(ST.tblOpen===undefined)ST.tblOpen=matchMedia('(min-width:1001px)').matches;
  main.innerHTML=`<div class="sx" data-step="${ST.step}">
   <div class="sx-bar"><div class="wrap sx-bar-in" id="sx-bar"></div><nav class="wrap sx-steps" id="sx-steps" aria-label="Steps"></nav></div>
   <div class="wrap sx-work">
    <div class="sx-tops" id="sx-chs">
     <section class="sx-tile sx-qtile" aria-label="The question"><label class="sx-qq"><span>Question</span><input id="sx-in-q" placeholder="Ask what a reader would ask" autocomplete="off"></label></section>
     <section class="sx-tile sx-qstile" aria-labelledby="sx-qtl"><div class="sx-orow"><h2 class="sx-olab" id="sx-qtl">Queries</h2><div class="sx-chrow" id="sx-qtabs" role="tablist" aria-labelledby="sx-qtl"></div></div></section>
     <section class="sx-tile sx-ctile" aria-labelledby="sx-ctl"><div class="sx-orow"><h2 class="sx-olab" id="sx-ctl">Charts</h2><div class="sx-chrow" id="sx-chrow" role="tablist" aria-labelledby="sx-ctl"></div></div><div class="sx-set"><label class="sx-field"><small>Short name, used in values</small><input id="sx-in-cn" autocomplete="off" spellcheck="false"></label><label class="sx-field"><small>Data from</small><select id="sx-in-cq"></select></label><span class="sx-cgo" id="sx-cgo"></span></div><div class="sx-layrow" id="sx-layrow"></div></section>
    </div>
    <div class="sx-panes">
     <section class="sx-pane" data-pane="query" aria-labelledby="sx-h1"${ST.step==='query'?'':' hidden'}>
      <div class="sx-qgrid${ST.tblOpen?'':' closed'}" id="sx-qgrid">
       <section class="sx-schema" id="sx-tables" aria-labelledby="sx-th"><header class="sx-schh"><h2 id="sx-th">Tables in the warehouse</h2><button type="button" class="sx-ib" id="sx-tclose" aria-label="Hide the tables" data-tip="Hide the tables">${SX_HIDEI}</button></header><div class="sx-tframe"><div class="sx-tbar"><span class="sx-findw">${SX_FIND}<input class="sx-find" id="sx-find" type="search" placeholder="Find a table or field" aria-label="Find a table or field" autocomplete="off" spellcheck="false" value="${sxEsc(ST.tblQ||'')}"></span><span class="sx-tcount" id="sx-tcount" aria-live="polite"></span></div><div class="sx-tl" id="sx-tl"></div></div></section>
       <div class="sx-step sx-qmain" id="sx-q"><header><span class="qn">1</span><h2 id="sx-h1" tabindex="-1">Query the warehouse</h2><span id="sx-qstate"></span><span class="sx-meta" id="sx-qmeta"></span><span class="sx-hact"><button class="ctl alt" type="button" id="sx-topen" aria-controls="sx-tables">${SX_TABLESI}Tables</button><button class="ctl alt" type="button" id="sx-fmt" title="One clause per line">Format</button><button class="ctl" type="button" id="sx-run"><span id="sx-runl">Run</span><kbd>${SX_MAC?'⌘':'Ctrl'} Enter</kbd></button></span></header>
        <p class="sx-lede">Write a query against the warehouse's gold tables and run it. Every chart that reads it, and the words around that chart, use the rows it returns.</p>
        <div class="sx-code"><pre id="sx-hl" aria-hidden="true"></pre><pre class="sx-flash" id="sx-flash" aria-hidden="true"></pre><textarea id="sx-sql" spellcheck="false" autocapitalize="off" aria-label="SQL query" aria-describedby="sx-sqlhelp"></textarea></div>
        <p class="sx-help" id="sx-sqlhelp">Queries run only when you press Run. ${SX_UNDO} undoes any change, even Format or a sample query, and ${SX_REDO} redoes it. Tab leaves the editor.</p><span class="sx-vh" id="sx-live" aria-live="polite"></span>
        <div class="sx-res" id="sx-res"></div>
       </div>
      </div>
     </section>
     <section class="sx-pane" data-pane="chart" aria-labelledby="sx-h2"${ST.step==='chart'?'':' hidden'}>
      <div class="sx-step" id="sx-c"><header><span class="qn">2</span><h2 id="sx-h2" tabindex="-1">Choose the chart</h2><span id="sx-cstate"></span><span class="sx-meta" id="sx-cmeta"></span></header>
       <p class="sx-lede">Pick the form that shows these rows best. The ones that fit come first, and the preview shows the chart as it will sit on its page.</p>
       <div class="sx-forms" id="sx-forms" role="radiogroup" aria-label="Chart form"></div>
       <div class="sx-fields" id="sx-fields"></div>
      </div>
     </section>
     <section class="sx-pane" data-pane="words" aria-labelledby="sx-h3"${ST.step==='words'?'':' hidden'}>
      <div class="sx-step" id="sx-w"><header><span class="qn">3</span><h2 id="sx-h3" tabindex="-1">Write the words</h2><span id="sx-wstate"></span></header>
       <p class="sx-lede">Write what a reader sees around the chart. Values in double braces fill in from the result, so the numbers cannot drift from the data.</p>
       <div class="sx-words">
        <div class="sx-tokens" id="sx-tok"></div>
        <fieldset class="sx-grp"><legend>Above the chart</legend>
         <label><span id="sx-l-f">Finding, shown as the headline</span><input id="sx-in-f" aria-labelledby="sx-l-f" aria-describedby="sx-ra-f" autocomplete="off"><span class="sx-ra" id="sx-ra-f"></span></label>
        </fieldset>
        <fieldset class="sx-grp"><legend>On the question card</legend>
         <div class="sx-two"><label>Answer<input id="sx-in-av" aria-describedby="sx-ra-av" autocomplete="off"></label><label>Its label<input id="sx-in-al" autocomplete="off"></label></div><span class="sx-ra" id="sx-ra-av"></span>
        </fieldset>
        <fieldset class="sx-cw" id="sx-cw" hidden><legend id="sx-cw-h"></legend><div class="sx-two"><label>Its title<input id="sx-in-cl" placeholder="Week by week" autocomplete="off"></label><label>Its key figure<input id="sx-in-ck" aria-describedby="sx-ra-ck" placeholder="{{weekly.latest}} kept" autocomplete="off"></label></div><span class="sx-ra" id="sx-ra-ck"></span></fieldset>
        <fieldset class="sx-grp"><legend>Under the chart</legend>
         <label><span class="sx-lrow"><span id="sx-rl">Reading under the chart</span><button type="button" class="sx-draftb" data-draft="read">Draft from the result</button></span><textarea id="sx-in-r" aria-labelledby="sx-rl" aria-describedby="sx-ra-r sx-rc" placeholder="What should a reader take from this chart, and what should they not read into it?"></textarea><span class="sx-ra" id="sx-ra-r"></span><small id="sx-rc"></small></label>
         <div id="sx-sugg"></div>
         <div class="sx-srcbox"><span class="sx-lab" id="sx-sl">Sources credited under the chart</span><div id="sx-srcs" role="group" aria-labelledby="sx-sl"></div><p class="sx-srcnote" id="sx-srcnote" aria-live="polite"></p></div>
        </fieldset>
        <fieldset class="sx-grp"><legend>For readers who cannot see the chart</legend>
         <label><span class="sx-lrow"><span id="sx-altl">Text alternative for the chart</span><button type="button" class="sx-draftb" data-draft="alt">Draft from the result</button></span><textarea id="sx-in-alt" aria-labelledby="sx-altl" aria-describedby="sx-ra-alt" rows="2" placeholder="What the chart shows, for readers who cannot see it"></textarea><span class="sx-ra" id="sx-ra-alt"></span></label>
        </fieldset>
       </div>
      </div>
     </section>
     <section class="sx-pane" data-pane="review" aria-labelledby="sx-h4"${ST.step==='review'?'':' hidden'}>
      <div class="sx-step" id="sx-r"><header><span class="qn">4</span><h2 id="sx-h4" tabindex="-1">Review and publish</h2><span id="sx-rstate"></span></header>
       <p class="sx-lede">Every check that must pass has to pass before the pull request opens. Each one links to the step that fixes it.</p>
       <div class="sx-rev">
        <section aria-labelledby="sx-chk-h"><h3 id="sx-chk-h">Before publishing</h3><ul class="sx-checks" id="sx-checks"></ul></section>
        <section aria-labelledby="sx-chg-h"><h3 id="sx-chg-h">What changes</h3><ul class="sx-files sx-chg" id="sx-changes"></ul></section>
        <p class="sx-note">Publishing opens a pull request with a query file for each chart and one analysis file. The build reruns every query and stops if a number on the page no longer matches the warehouse.</p>
       </div>
      </div>
     </section>
    </div>
    <aside class="sx-prev" aria-label="Preview"><div class="sx-prevh"><h2>On its subject page</h2><span class="sx-seg" role="group" aria-label="Preview width"><button type="button" data-dev="desktop" aria-pressed="true">Desktop</button><button type="button" data-dev="phone" aria-pressed="false">Phone</button></span></div><div class="sx-card" id="sx-card"></div><div class="sx-deckw"><h2>On its question card</h2><div id="sx-deck"></div></div></aside>
    <div class="sx-foot" id="sx-foot"></div>
   </div>
  </div>`;
  sxPaint();
  const root=main.querySelector('.sx'),F={'sx-in-q':[()=>ST,'q'],'sx-in-f':[()=>ST,'f'],'sx-in-av':[()=>ST,'av'],'sx-in-al':[()=>ST,'al'],'sx-in-cl':[sxC,'label'],'sx-in-ck':[sxC,'key'],'sx-in-r':[sxOwner,'read'],'sx-in-alt':[sxC,'alt']};
  const pickChart=i=>{ST.cur=Math.max(0,Math.min(ST.charts.length-1,i));const qi=ST.queries.findIndex(q=>q.id===sxC().qid);if(qi>=0)ST.qcur=qi;ST.sugg=null;sxPaintCharts();sxPaintQuery();sxPaintChart();sxPaintWords();sxPaintPreview();sxPaintChecks()};
  /* A check's "Go to it" opens the step that holds the field, then brings the field into view */
  const goTo=id=>{const el=document.getElementById(id);if(!el)return;const p=el.closest('[data-pane]');if(p&&p.dataset.pane!==ST.step)sxGo(p.dataset.pane,{focus:false});
   requestAnimationFrame(()=>{el.scrollIntoView({behavior:LCC.reduce()?'auto':'smooth',block:'center'});const f=/^(INPUT|TEXTAREA)$/.test(el.tagName)?el:el.matches('.sx-step')?el.querySelector('header h2'):el.querySelector('button,input,textarea');if(f)setTimeout(()=>f.focus({preventScroll:true}),300)})};
  /* The bar's height sets where sticky panels stop, and it changes when the bar wraps */
  const bar=root.querySelector('.sx-bar'),barH=()=>root.style.setProperty('--sx-bar-h',bar.offsetHeight+'px');barH();new ResizeObserver(barH).observe(bar);
  const runLabel=()=>{const ta=$('#sx-sql');$('#sx-runl').textContent=ta.selectionEnd>ta.selectionStart?'Run selection':'Run'};
  const run=()=>{const ta=$('#sx-sql'),sel=ta.selectionEnd>ta.selectionStart?ta.value.slice(ta.selectionStart,ta.selectionEnd):null;sxRun(sel)};
  root.addEventListener('click',e=>{
   /* Tabs in the preview pick the chart to edit, rather than reaching the page's own handler */
   const pt=e.target.closest('#sx-card .ctab');if(pt){e.stopPropagation();pickChart(+pt.dataset.chart.slice(1));return}
   const b=e.target.closest('button,a');if(!b)return;
   if(b.dataset.step){sxGo(b.dataset.step);return}
   if(b.id==='sx-tclose'){ST.tblOpen=false;$('#sx-qgrid').classList.add('closed');$('#sx-topen').focus();return}
   if(b.id==='sx-topen'){ST.tblOpen=true;$('#sx-qgrid').classList.remove('closed');sxPaintTables();$('#sx-find').focus({preventScroll:true});return}
   if(b.dataset.ci){pickChart(+b.dataset.ci);return}
   if(b.dataset.rm){const i=+b.dataset.rm,gone=ST.charts[i];ST.charts.splice(i,1);if(ST.cur>=i&&ST.cur>0)ST.cur--;if(ST.charts.length===1)ST.layout='One chart';sxPaint();toast(`${gone.label||gone.name} removed. Values that named it now show as broken in the checks.`);return}
   if(b.id==='sx-addc'){const c=sxC(),n=sxMk({qid:c.qid,src:c.src,srcAuto:sxAuto(c)});n.name=sxUniq(`chart${ST.charts.length+1}`);n.form=sxSuggestC(n)||c.form;ST.charts.push(n);ST.cur=ST.charts.length-1;if(ST.layout==='One chart')ST.layout='One below another';sxPaint();$('#sx-in-cn').focus();$('#sx-in-cn').select();toast(`${n.name} added. It reads ${sxQName(n.qid)}; pick another under Data from.`);return}
   if(b.id==='sx-addq'){const q=sxMkQ({name:sxUniqQ(`query${ST.queries.length+1}`),sql:'select *\nfrom gold.\nlimit 100;',runNote:'Write a query that reads a table, then run it.'});ST.queries.push(q);ST.qcur=ST.queries.length-1;if(ST.step!=='query')sxGo('query',{focus:false});sxPaint();sxFocusSql();toast(`${q.name} added. Write it and run it, then add a chart from it.`);return}
   if(b.id==='sx-qaddc'){const q=sxQ(),n=sxMk({qid:q.id,src:[],srcAuto:true});n.name=sxUniq(`chart${ST.charts.length+1}`);n.form=sxSuggestC(n)||'Bars';ST.charts.push(n);ST.cur=ST.charts.length-1;if(ST.layout==='One chart')ST.layout='One below another';sxPaint();sxGo('chart');toast(`${n.name} added from ${q.name}.`);return}
   if(b.dataset.qi){ST.qcur=+b.dataset.qi;sxPaintCharts();sxPaintQuery();sxPaintSteps();sxPaintFoot();return}
   if(b.dataset.qrm){const i=+b.dataset.qrm,q=ST.queries[i],users=ST.charts.filter(c=>c.qid===q.id);if(users.length){toast(`${q.name} feeds ${sxList(users.map(c=>c.label||c.name))}. Point ${users.length===1?'that chart':'those charts'} at another query first.`);return}ST.queries.splice(i,1);if(ST.qcur>=i&&ST.qcur>0)ST.qcur--;sxPaint();toast(`${q.name} removed.`);return}
   if(b.dataset.qren){sxQRenStart(+b.dataset.qren);return}
   if(b.dataset.qrenok){sxQRename(true,true);return}
   if(b.dataset.goq){ST.qcur=+b.dataset.goq;sxPaintCharts();sxPaintQuery();sxGo('query');return}
   if(b.dataset.lay){ST.layout=b.dataset.lay;sxPaint();return}
   if(b.dataset.dev){ST.device=b.dataset.dev;root.querySelectorAll('[data-dev]').forEach(x=>x.setAttribute('aria-pressed',x.dataset.dev===ST.device));sxPaintPreview();return}
   if(b.id==='sx-run'||b.hasAttribute('data-run')){run();return}
   if(b.id==='sx-fmt'){const c=sxQ(),v=sxFormat(c.sql);sxEditSql(c,v,v.length,v.length);sxFocusSql();return}
   if(b.dataset.sort){const c=sxQ(),i=+b.dataset.sort,first=sxType(c.res,i)==='text'?1:-1;c.sort=!c.sort||c.sort.i!==i?{i,d:first}:c.sort.d===first?{i,d:-first}:null;sxSortApply(c);return}
   if(b.dataset.topen){sxOpenTable(b.dataset.topen);return}
   if(b.hasAttribute('data-tback')){sxCloseTable();return}
   if(b.hasAttribute('data-tmore')){const d=$('#sx-tdd'),open=b.getAttribute('aria-expanded')!=='true';d.classList.toggle('clamp',!open);b.setAttribute('aria-expanded',open);b.textContent=open?'Show less':'Show all';return}
   if(b.dataset.tins){sxInsert(sxQ(),'gold.'+b.dataset.tins,true);return}
   if(b.dataset.fins){sxInsert(sxQ(),b.dataset.fins,false,true);return}
   if(b.dataset.tsam){const t=b.dataset.tsam,c=sxQ(),v=sxSample(t),mine=!sxStarter(c.sql),at=v.indexOf('*')+1;if(sxEditSql(c,v,at,at)){sxFlash(c,0,v.length);if(mine)toast(`The query now reads a sample of ${t}. ${SX_UNDO} in the editor brings yours back.`)}sxFocusSql();return}
   if(b.dataset.tshow){sxShowTable(b.dataset.tshow);return}
   if(b.dataset.form){if(b.getAttribute('aria-disabled')==='true'){toast(`${b.dataset.form}: ${b.querySelector('.why')?b.querySelector('.why').textContent:'needs a different result'}.`);return}sxC().form=b.dataset.form;sxPaintCharts();sxPaintChart();sxPaintWords();sxPaintPreview();sxPaintChecks();return}
   if(b.dataset.val){const c=sxC(),i=+b.dataset.val,off=c.enc.off;if(off.includes(i))c.enc.off=off.filter(x=>x!==i);else if(c.res.spec.series.length-off.length>1)c.enc.off=[...off,i];else{toast('A chart needs at least one value.');return}if(!sxFitsC(c,c.form))c.form=sxSuggestC(c);sxPaintChart();sxPaintWords();sxPaintPreview();sxPaintChecks();return}
   if(b.id==='sx-choose'){const c=sxC(),s=sxSuggestC(c);if(s){c.form=s;sxPaintCharts();sxPaintChart();sxPaintPreview();sxPaintChecks()}return}
   if(b.id==='sx-reset'){const c=sxC();c.form=c.own||sxSuggestC(c)||c.form;c.enc={off:[],label:null,value:null,top:10};c.ends=true;sxPaintCharts();sxPaintChart();sxPaintWords();sxPaintPreview();sxPaintChecks();return}
   if(b.dataset.tok){const act=document.activeElement,el=act&&F[act.id]?act:$(ST.last)||$('#sx-in-f'),tok=`{{${b.dataset.tok}}}`,i=el.selectionStart??el.value.length,j=el.selectionEnd??el.value.length;el.value=el.value.slice(0,i)+tok+el.value.slice(j);el.focus();el.setSelectionRange(i+tok.length,i+tok.length);el.dispatchEvent(new Event('input',{bubbles:true}));return}
   if(b.dataset.draft){const c=sxC(),text=b.dataset.draft==='read'?sxReadDraft(c):sxAltDraft(c);if(!text){toast('Run the query first, so the draft has values to use.');return}ST.sugg={field:b.dataset.draft,text};sxPaintWords();return}
   if(b.id==='sx-sugg-ok'){const s=ST.sugg;if(s.field==='read')sxOwner().read=s.text;else sxC().alt=s.text;ST.sugg=null;sxPaintWords();sxPaintPreview();sxPaintChecks();return}
   if(b.id==='sx-sugg-no'){ST.sugg=null;sxPaintWords();return}
   if(b.dataset.src&&b.classList.contains('sx-src')){const o=sxOwner(),id=b.dataset.src;o.src=o.src.includes(id)?o.src.filter(x=>x!==id):[...o.src,id];o.srcAuto=false;sxPaintSources();$(`#sx-srcs [data-src="${id}"]`)?.focus();sxPaintPreview();sxPaintChecks();return}
   if(b.id==='sx-srcauto'){const o=sxOwner();o.srcAuto=true;sxPaintSources();sxPaintPreview();sxPaintChecks();$('#sx-srcs .sx-src')?.focus();toast(`Credits now follow the query: ${sxList(o.src.map(id=>VZ.sourceInfo(id).name))}.`);return}
   if(b.dataset.go){goTo(b.dataset.go);return}
   if(b.id==='sx-discard'){if(confirm('Discard every unpublished change to this question?')){sxLoad(ST.aid);sxMark0();sxPaint();toast('Changes discarded. The question is back to its published version.')}return}
   if(b.id==='sx-pub'||b.classList.contains('sx-pubgo')){const act=b.dataset.act;if(act==='none'){toast('Edit the question first. There is nothing new to publish.');return}if(act==='checks'){const first=sxFirstIssue();if(first)goTo(first[3]);else sxGo('review');return}sxOpenPanel();return}
  });
  root.addEventListener('keydown',e=>{
   if(e.target.id==='sx-qren-in'){if(e.key==='Enter'){e.preventDefault();sxQRename(true,true)}else if(e.key==='Escape'){e.preventDefault();sxQRename(false,true)}return}
   const pt=e.target.closest&&e.target.closest('#sx-card .ctab');
   if(pt){e.stopPropagation();const to={ArrowRight:1,ArrowLeft:-1}[e.key];if(to){e.preventDefault();pickChart((ST.cur+to+ST.charts.length)%ST.charts.length)}return}
   if(ST.pal&&ST.pal.el===e.target){const p=ST.pal;if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();p.on=(p.on+(e.key==='ArrowDown'?1:-1)+p.items.length)%p.items.length;p.box.querySelectorAll('[data-pi]').forEach((x,i)=>{x.setAttribute('aria-selected',i===p.on);if(i===p.on)x.scrollIntoView({block:'nearest'})});return}if(e.key==='Enter'){e.preventDefault();sxPalettePick(p.on);return}if(e.key==='Escape'){e.preventDefault();sxPaletteClose();return}}
   if(e.key==='Escape'&&ST.tblSel&&e.target.closest&&e.target.closest('#sx-tl')){e.preventDefault();sxCloseTable();return}
   const k=(e.key||'').toLowerCase();
   if((e.metaKey||e.ctrlKey)&&!e.altKey&&(k==='z'||(k==='y'&&!SX_MAC))&&(e.target.id==='sx-sql'||(e.target.closest('#sx-q')&&!/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)))){e.preventDefault();sxUndo(k==='y'||e.shiftKey);return}
   if(e.target.id==='sx-sql'&&(e.metaKey||e.ctrlKey)&&e.key==='Enter'){e.preventDefault();run()}
  });
  /* The browser's own undo for the editor (its Edit menu) runs through the same history */
  root.addEventListener('beforeinput',e=>{const t=e.target;if(t.id!=='sx-sql')return;if(/^history(Undo|Redo)$/.test(e.inputType)){e.preventDefault();sxUndo(e.inputType==='historyRedo');return}sxNoteTyping(sxQ(),t,e.inputType,e.data)});
  root.addEventListener('input',e=>{
   const t=e.target;
   if(t.id==='sx-sql'){const c=sxQ(),was=c.stale;$('#sx-flash').innerHTML='';c.sql=t.value;c.caret=[t.selectionStart,t.selectionEnd];sxHist(c).end=t.selectionEnd;sxAfterSql(c,was);return}
   if(t.id==='sx-find'){ST.tblQ=t.value;ST.tblSel=null;sxPaintTables();return}
   if(t.id==='sx-in-cn'){const c=sxC(),old=c.name,nw=sxUniq(sxSlug(t.value)||old,c);if(nw&&nw!==old){c.name=nw;const fix=s=>String(s||'').replaceAll(`{{${old}.`,`{{${nw}.`);ST.f=fix(ST.f);ST.av=fix(ST.av);ST.al=fix(ST.al);ST.read=fix(ST.read);ST.charts.forEach(x=>{x.key=fix(x.key);x.read=fix(x.read);x.alt=fix(x.alt)});sxSoon(()=>{sxPaintCharts();sxPaintWords();sxPaintPreview();sxPaintChecks()})}return}
   const m=F[t.id];if(!m)return;
   /* {{2.latest}} is a shortcut: it becomes the chart's name as soon as it is typed */
   if(/\{\{\s*\d+\./.test(t.value)){const at=t.selectionStart,before=sxNameRefs(t.value.slice(0,at));t.value=before+sxNameRefs(t.value.slice(at));t.setSelectionRange(before.length,before.length)}
   m[0]()[m[1]]=t.value;ST.last='#'+t.id;
   if(/\{\{[a-z0-9_.]*$/i.test(t.value.slice(0,t.selectionStart)))sxPalette(t);else sxPaletteClose();
   sxReadsAs();
   if(t.id==='sx-in-q')sxPaintBar();
   if(t.id==='sx-in-cl')sxPaintCharts();
   sxSoon(()=>{sxPaintPreview();sxPaintChecks();$('#sx-wstate').innerHTML=sxStateHtml(sxStepState('words'))});
  });
  root.addEventListener('change',e=>{
   /* Pointing a chart at another query: its values start again, and its form changes only if it no longer fits */
   if(e.target.id==='sx-in-cq'){const c=sxC();c.qid=e.target.value;c.enc={off:[],label:null,value:null,top:10};if(c.res&&!sxFitsC(c,c.form))c.form=sxSuggestC(c)||c.form;ST.qcur=Math.max(0,ST.queries.findIndex(q=>q.id===c.qid));sxPaint();$('#sx-in-cq').focus();toast(`${c.label||c.name} now reads ${sxQName(c.qid)}.`);return}
   if(e.target.id==='sx-ends'){sxC().ends=e.target.checked;sxPaintPreview();return}
   const k=e.target.dataset.enc;if(k){const c=sxC();c.enc[k]=+e.target.value;if(!sxFitsC(c,c.form))c.form=sxSuggestC(c);sxPaintChart();sxPaintWords();sxPaintPreview();sxPaintChecks()}
  });
  ['select','keyup','mouseup'].forEach(ev=>root.addEventListener(ev,e=>{if(e.target.id==='sx-sql'){runLabel();sxQ().caret=[e.target.selectionStart,e.target.selectionEnd]}}));
  root.addEventListener('focusin',e=>{if(F[e.target.id])ST.last='#'+e.target.id});
  root.addEventListener('focusout',e=>{if(ST.pal&&ST.pal.el===e.target)setTimeout(()=>{if(ST.pal&&document.activeElement!==ST.pal.el)sxPaletteClose()},120)});
  /* A value chip keeps the caret where it is, so the value lands in the field being written */
  root.addEventListener('mousedown',e=>{if(e.target.closest('.sx-tok,[data-qrenok]'))e.preventDefault()});
  /* A double-click on a query's tile renames it; leaving the field keeps what was typed */
  root.addEventListener('dblclick',e=>{const t=e.target.closest&&e.target.closest('#sx-qtabs [data-qi]');if(t){e.preventDefault();sxQRenStart(+t.dataset.qi)}});
  root.addEventListener('focusout',e=>{if(e.target.id==='sx-qren-in')setTimeout(()=>{if(ST.qren!=null&&document.activeElement!==$('#sx-qren-in'))sxQRename(true,false)},0)});
  const tick=setInterval(()=>{const s=main.querySelector('.sx-strip span:last-child');if(s&&sxQ()&&sxQ().ranAt)s.textContent=sxAgo(sxQ().ranAt)},20000);
  sxTips(root);
  /* The value palette follows its field when the page scrolls */
  const palMove=()=>{const p=ST.pal;if(!p)return;const r=p.el.getBoundingClientRect();if(r.bottom<0||r.top>innerHeight){sxPaletteClose();return}const bh=p.box.offsetHeight;p.box.style.top=(r.bottom+4+bh>innerHeight&&r.top-4-bh>8?r.top-4-bh:r.bottom+4)+'px'};
  addEventListener('scroll',palMove,{passive:true});
  cleanup.push(()=>{clearInterval(tick);removeEventListener('scroll',palMove);sxPaletteClose();document.querySelector('.sx-tip')?.remove();document.querySelector('.sx-dlg')?.remove();ST.handles.forEach(h=>h&&h.destroy&&h.destroy());ST.handles=[]});
 },
});
