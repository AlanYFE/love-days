import {MobileYear} from './mobile-year.jsx';
import {CommentDrafts} from './comments.jsx';
import {DayPanel,useMobileLayout} from './day-panel.jsx';
import MonthlyMemories from './monthly-memories.jsx';
import {api} from './api.mjs';
import {EmojiContext,EmojiPicker} from './emoji-picker.jsx';
import {EntryCard} from './entry-card.jsx';
import {MonthSelector} from './month-selector.jsx';
import {PhotoViewer} from './photo-viewer.jsx';
import {EditEntry} from './edit-entry.jsx';
import React, {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './noop.js';
import TagPicker from './tags.jsx';
import {createRequestGate} from './request-gate.mjs';
import ActivityCenter from './activities.jsx';
import LocationPicker from './locations.jsx';
import {LiveUploads} from './live-photos.jsx';
import {uploadItems} from './live-upload.mjs';
import {chinaToday,daysBetween,eventsForYear,upcomingEvents} from './anniversaries.mjs';
const localDay=(d)=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const level=n=>Math.min(3,Math.max(0,n));
const pretty=d=>{
 const date=new Date(d+'T12:00:00');
 return date.toLocaleDateString('zh-CN',{month:'long',day:'numeric'})+' · '+date.toLocaleDateString('zh-CN',{weekday:'long'});
};
function App(){
 const mobile=useMobileLayout();
 const [dayOpen,setDayOpen]=useState(false);
 const [monthlyOpen,setMonthlyOpen]=useState(false);
 const requestGate=React.useRef(null);if(!requestGate.current)requestGate.current=createRequestGate();
 useEffect(()=>()=>requestGate.current.invalidate(),[]);
 const [location,setLocation]=useState(null);
 const [today,setToday]=useState(()=>chinaToday());
 const [anniversaries,setAnniversaries]=useState(null);
 useEffect(()=>{const update=()=>setToday(chinaToday());const timer=setInterval(update,30000);window.addEventListener('focus',update);return()=>{clearInterval(timer);window.removeEventListener('focus',update)}},[]);

 const [liveOptions,setLiveOptions]=useState([]),[liveDetecting,setLiveDetecting]=useState(false);
 const [postTags,setPostTags]=useState([]),[tagBusy,setTagBusy]=useState(false);
 const [editing,setEditing]=useState(null);
 const [gallery,setGallery]=useState(null);
 const [emojis,setEmojis]=useState([]);
 async function reloadEmojis(){setEmojis(await api('/api/emojis'))}
 const [me,setMe]=useState(null),[loading,setLoading]=useState(true),[entries,setEntries]=useState([]),[error,setError]=useState('');
 const [month,setMonth]=useState(()=>new Date(today.slice(0,7)+'-01T12:00:00')),[view,setView]=useState('month'),[selected,updateSelected]=useState(today),[compose,setCompose]=useState(false),[saving,setSaving]=useState(false),[progress,setProgress]=useState(0),[files,setFiles]=useState([]);
 const [overview,setOverview]=useState({days:[],stats:{days:0,entries:0,media:0}});
 const [loadedDay,setLoadedDay]=useState(null),[dayLoading,setDayLoading]=useState(false),[dayError,setDayError]=useState('');
 const selectedRef=React.useRef(selected);
 function setSelected(day){if(selectedRef.current!==day){requestGate.current.invalidate();selectedRef.current=day;setDayError('')}updateSelected(day)}
 useEffect(()=>{if(!me){setAnniversaries(null);return}let active=true;api('/api/anniversaries').then(data=>{if(active)setAnniversaries(data)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[me]);
 async function refresh(day=selectedRef.current){
  const current=requestGate.current.begin();setDayLoading(true);setDayError('');
  try{const [summary,result]=await Promise.all([api('/api/calendar'),api('/api/entries?day='+encodeURIComponent(day))]);if(current()&&selectedRef.current===day){setOverview(summary);setEntries(result);setLoadedDay(day)}}
  catch(e){if(current()){setDayError(e.message);throw e}}
  finally{if(current())setDayLoading(false)}
 }
 useEffect(()=>{if(me)refresh().catch(()=>{});return()=>requestGate.current.invalidate()},[me,selected]);
 useEffect(()=>{if(me)reloadEmojis().catch(e=>setError(e.message));else setEmojis([])},[me]);
 useEffect(()=>{api('/api/me').then(u=>setMe(u)).catch(e=>{if(e.message!=='请先登录')setError(e.message)}).finally(()=>setLoading(false))},[]);
 useEffect(()=>{if(!me)return;let active=true,inflight=false;async function tick(){if(!active||inflight||document.hidden)return;inflight=true;try{await refresh()}catch{}finally{inflight=false}}const id=setInterval(tick,30000);window.addEventListener('focus',tick);document.addEventListener('visibilitychange',tick);return()=>{active=false;clearInterval(id);window.removeEventListener('focus',tick);document.removeEventListener('visibilitychange',tick)}},[me]);
 async function login(e){e.preventDefault();setError('');const f=new FormData(e.target);try{setSaving(true);requestGate.current.invalidate();setMe(await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(f))}))}catch(e){setError(e.message)}finally{setSaving(false)}}
 const byDay=React.useMemo(()=>Object.fromEntries(overview.days.map(d=>[d.day,d])),[overview]);
 const daily=loadedDay===selected?entries:[],y=month.getFullYear(),m=month.getMonth();
 const specialDays=React.useMemo(()=>{const map={};for(const e of eventsForYear(anniversaries,y))(map[e.day]??=[]).push(e);return map},[anniversaries,y]);
 const selectedEvents=eventsForYear(anniversaries,Number(selected.slice(0,4))).filter(e=>e.day===selected);
 const upcoming=upcomingEvents(anniversaries,today);
 function jumpDay(day,reveal=true){setDayOpen(reveal);setSelected(day);setMonth(new Date(day.slice(0,7)+'-01T12:00:00'));setView('month')}
 const prefix=view==='month'?`${y}-${String(m+1).padStart(2,'0')}`:String(y);
 const recent=overview.days.reduce((latest,d)=>d.count>0 && d.day>latest ? d.day : latest,'');
 const scoped=overview.days.filter(e=>e.day.startsWith(prefix)).reduce((n,d)=>n+d.count,0);
 function cover(day){return byDay[day]?.cover}
 function stepDay(delta){const d=new Date(selected+'T12:00:00');d.setDate(d.getDate()+delta);if(d.getFullYear()>=1900&&d.getFullYear()<=2200)jumpDay(localDay(d))}
 function shift(n){
  const target=new Date(y+(view==='year'?n:0),m+(view==='month'?n:0),1);
  if(target.getFullYear()<1900 || target.getFullYear()>2200)return;
  const lastDay=new Date(target.getFullYear(),target.getMonth()+1,0).getDate();
  const picked=new Date(target.getFullYear(),target.getMonth(),Math.min(Number(selected.slice(-2)),lastDay));
  setMonth(target);
  setSelected(localDay(picked));
 }
 function dayButton(date,mini=false){
  const day=localDay(date);
  const count=byDay[day]?.count||0;
  const photo=mini?null:cover(day);
  const occasions=specialDays[day]||[];
  const description=occasions.map(event=>event.label).join(' · ');
  const selectedDay=day===selected;
  const isToday=day===today;
  const classes=['day','l'+level(count),selectedDay&&'selected',isToday&&'today',mini&&'mini',occasions.length>0&&'special-day'].filter(Boolean).join(' ');
  return <button type="button" key={day} className={classes} onClick={()=>{setSelected(day);setDayOpen(true)}}
   title={`${day} · ${count} 条记录${description?' · '+description:''}`}
   aria-label={`${day}，${count} 条记录${description?'，'+description:''}`}
   aria-pressed={selectedDay} aria-current={isToday?'date':undefined}>
   {photo&&<img src={photo.thumb} loading="lazy" alt=""/>}
   {!mini&&<>
    {occasions.length>0&&<span className="special-mark" aria-hidden="true"/>}
    <span className="daynum">{date.getDate()}</span>
    {photo?.kind==='video'&&<span className="play" aria-hidden="true">▷</span>}
    {!photo&&count>0&&<>
     <span className="daycount">{count}<span className="countlabel"> 条</span></span>
     <span className="excerpt">{byDay[day]?.excerpt||'一段小回忆'}</span>
    </>}
   </>}
  </button>;
 }
 async function visitActivity(item){
  const current=requestGate.current.begin();
  const target=await api('/api/entries/'+encodeURIComponent(item.entry_id));
  const [latest,summary]=await Promise.all([api('/api/entries?day='+encodeURIComponent(target.day)),api('/api/calendar')]);
  if(!current())throw Error('列表刚刚更新，请再点一次动态');
  const entry=latest.find(e=>e.id===item.entry_id);
  if(!entry||item.comment_id&&!entry.comments.some(c=>c.id===item.comment_id))throw Error('这条帖子或评论已删除，请刷新动态列表。');
  jumpDay(entry.day,false);setOverview(summary);setEntries(latest);setLoadedDay(entry.day);setDayLoading(false);setDayError('');
  return ()=>{setDayOpen(true);requestAnimationFrame(()=>requestAnimationFrame(()=>{const node=document.getElementById(item.comment_id?'comment-'+item.comment_id:'entry-'+item.entry_id);if(node){const folded=node.closest('details');if(folded)folded.open=true;node.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'});node.focus({preventScroll:true})}}))};
 }
 async function remove(e){if(!confirm('确定删除这条记录、附件及其下所有评论？此操作无法撤销。'))return;try{await api('/api/entries/'+e.id,{method:'DELETE'});await refresh()}catch(e){setError(e.message)}}
 function save(e){e.preventDefault();if(saving||tagBusy||liveDetecting)return;setError('');if(location&&!location.name.trim()){setError('请填写地点名称，或移除地点');return}const form=new FormData(e.target);form.set('location',JSON.stringify(location));form.set('tag_ids',JSON.stringify(postTags.map(t=>t.id)));const items=uploadItems(files,liveOptions);const allFiles=items.flatMap(({file,option:o})=>o.enabled&&o.pair?[file,o.pair]:[file]);if(items.length>12||allFiles.some(f=>f.size>100*1024*1024)||allFiles.reduce((n,f)=>n+f.size,0)>200*1024*1024){setError('最多 12 个附件；单个 100 MB，合计 200 MB。');return}form.delete('files');items.forEach(({file})=>form.append('files',file));form.set('live_options',JSON.stringify(items.map(({option:o})=>({enabled:!!o.enabled,paired:!!(o.enabled&&o.pair)}))));items.forEach(({option:o},i)=>{if(o.enabled&&o.pair)form.append('live_'+i,o.pair)});setSaving(true);setProgress(0);const xhr=new XMLHttpRequest();xhr.open('POST','/api/entries');xhr.setRequestHeader('X-Blue-Request','1');xhr.upload.onprogress=e=>{if(e.lengthComputable)setProgress(Math.round(e.loaded/e.total*100))};xhr.onerror=()=>{setSaving(false);setError('网络连接中断，请检查当天记录后重试，避免重复发布。')};xhr.onload=async()=>{try{let data;try{data=JSON.parse(xhr.responseText)}catch{throw Error('上传失败，可能超过服务器限制')}if(xhr.status>=400)throw Error(typeof data.detail==='string'?data.detail:'上传失败');setSelected(form.get('day'));const d=new Date(form.get('day')+'T12:00:00');setMonth(new Date(d.getFullYear(),d.getMonth(),1));setCompose(false);setDayOpen(true);setFiles([]);await refresh()}catch(e){setError(e.message)}finally{setSaving(false)}};xhr.send(form)}
 if(loading)return <div className="loading">正在打开我们的日历…</div>;
 if(!me)return <main className="login"><div className="login-art"><div className="brand">Love Days<span className="brand-dot">.</span></div><h1>把平凡的日子，<br/>慢慢写进日历。</h1><p>两个人，一本日历。<br/>照片、心情，还有那些值得记住的小事。</p><div className="art-grid" aria-hidden="true">{Array.from({length:77},(_,i)=><i key={i} className={'l'+([0,1,2,3,4,0,2,1,3,0,4][i%11])}/>)}</div><small>OUR LITTLE CORNER OF THE WORLD</small></div><section className="login-form"><span className="eyebrow">ONLY US · 两个人的空间</span><h2>欢迎回家</h2><p>用你的账号，打开属于我们的每一天。</p><form onSubmit={login}><label>账号<input required name="username" autoComplete="username" placeholder="你的登录账号" maxLength={100}/></label><label>密码<input required type="password" name="password" autoComplete="current-password" placeholder="输入密码" maxLength={256}/></label>{error&&<p role="alert" className="error">{error}</p>}<button className="primary" disabled={saving}>{saving?'正在登录…':'打开我们的日历 →'}</button></form><small>仅限两位成员登录 · 照片和记录不公开</small></section></main>;
 const calendar=[];const first=(new Date(y,m,1).getDay()+6)%7;for(let i=0;i<first;i++)calendar.push(<div key={'blank'+i}/>);for(let d=1;d<=new Date(y,m+1,0).getDate();d++)calendar.push(dayButton(new Date(y,m,d)));
 const yearDays=[];for(let i=0;i<(new Date(y,0,1).getDay()+6)%7;i++)yearDays.push(<i key={'pad'+i}/>);for(let d=new Date(y,0,1);d.getFullYear()===y;d.setDate(d.getDate()+1))yearDays.push(dayButton(new Date(d),true));
 const summary=<>
  {anniversaries&&<section className="anniversary-panel" aria-label="我们的纪念日"><div className="anniversary-heading"><div><span className="eyebrow">日子慢慢，我们长长</span><h2>{daysBetween(anniversaries.together,today)>=0?<>在一起的第 <strong>{daysBetween(anniversaries.together,today)}</strong> 天</>:'等待我们的第一天'}</h2></div><span>从 {anniversaries.together.replaceAll('-',' · ')} 开始</span></div><div className="upcoming-days">{upcoming.map(e=><button type="button" key={e.id} onClick={()=>jumpDay(e.day)}><span className="occasion-icon" aria-hidden="true">{e.kind==='birthday'?'🎂':'♥'}</span><span><strong>{e.label}</strong><small>{e.day.replaceAll('-','.')}</small></span><b>{e.day===today?'就是今天':`还有 ${daysBetween(today,e.day)} 天`}</b></button>)}</div><p className="hint">公历生日 · 每半年与周年 · 每 100 天纪念日。相恋当天算第 0 天，倒计时按北京时间。</p></section>}
  <section className="stats"><div><strong>{overview.stats.days}</strong><span>个有回忆的日子</span></div><div><strong>{overview.stats.entries}</strong><span>条共同收藏</span></div><div><strong>{overview.stats.media}</strong><span>张照片与段视频</span></div></section>
 </>;
 return <CommentDrafts key={me.id}><EmojiContext.Provider value={{emojis,reloadEmojis}}><header><a className="brand" href="/">Love Days<span className="brand-dot">.</span> <small>两个人的摄影手账</small></a><div className="account"><span className="avatar">{me.name.slice(0,1)}</span><span>{me.name}</span><button className="textbtn" onClick={async()=>{try{await api('/api/logout',{method:'POST'});requestGate.current.invalidate();setMe(null);setDayOpen(false);setMonthlyOpen(false);setEntries([]);setLoadedDay(null);setOverview({days:[],stats:{days:0,entries:0,media:0}});setDayError('');setGallery(null);setEditing(null)}catch(e){setError(e.message)}}}>退出</button></div></header><main className="shell"><section className="intro">{mobile?<h1 className="mobile-journal-title">{anniversaries&&daysBetween(anniversaries.together,today)>=0?`在一起的第 ${daysBetween(anniversaries.together,today)} 天`:'我们的照片手账'}</h1>:<div><span className="eyebrow">{me.name}，欢迎回到我们的日子</span><h1>把日常，<br className="mobile-break"/>留给未来的我们<span>。</span></h1><p>照片、碎碎念，还有一起走过的每一天。</p></div>}<div className="intro-actions"><button type="button" className="textbtn" onClick={()=>setMonthlyOpen(true)}>月度回忆</button><EmojiPicker label="☺ 表情库"/><button className="primary" onClick={()=>{jumpDay(today,false);setFiles([]);setPostTags([]);setLocation(null);setDayOpen(false);setCompose(true);setError('')}}>＋ 记下今天</button></div></section><ActivityCenter key={me.id} request={api} onVisit={visitActivity}/>{!mobile&&summary}{error&&!compose&&<p role="alert" className="error">{error}</p>}<div className="workspace"><section className="calendar panel"><div className="journal-section-label"><span>我们的照片月历</span><button type="button" onClick={()=>jumpDay(today)}>回到今天 ↗</button></div><div className="calendar-toolbar"><div className="month-nav"><button onClick={()=>shift(-1)} aria-label="上一页">‹</button><MonthSelector month={month} view={view} onChange={d=>{setMonth(d);setSelected(localDay(d))}}/><button onClick={()=>shift(1)} aria-label="下一页">›</button></div><div className="tabs"><button className={view==='month'?'active':''} onClick={()=>setView('month')}>照片月历</button><button className={view==='year'?'active':''} onClick={()=>setView('year')}>全年热力图</button></div></div>{view==='month'?<>{!scoped && recent && <button type="button" className="recent-memory" onClick={()=>jumpDay(recent)}>这个月还没有记录 · 看看最近一条回忆（{recent.replaceAll('-','/')}） ↗</button>}<div className="weekdays">{'一二三四五六日'.split('').map(d=><span key={d}>{d}</span>)}</div><div className="month-grid">{calendar}</div></>:mobile?<MobileYear year={y} byDay={byDay} onChoose={date=>jumpDay(localDay(date),false)}/>:<><p className="muted">每一格是一天 · 从左到右为每周，周一在上</p><div className="year-scroll"><div className="year-grid">{yearDays}</div></div></>}<footer className="legend"><span>{view==='month'?'本月':'本年'} {scoped} 条记录</span><div>少 {[0,1,2,3].map(x=><i key={x} className={'l'+x} title={['0','1','2','3+'][x]+' 条'}/>)} 多</div></footer><p className="hint">1 条淡蓝 · 2 条中蓝 · 3 条及以上深蓝。{view==='month'?'陶土色小圆点标记纪念日和生日。':mobile?'':'陶土色边框标记纪念日和生日。'}</p><div className="calendar-occasions" aria-label="当前日历的纪念日">{Object.values(specialDays).flat().filter(e=>view==='year'||e.day.startsWith(prefix)).map(e=><button type="button" key={e.id} onClick={()=>jumpDay(e.day)}>{e.kind==='birthday'?'🎂':'♥'} {e.day.slice(5).replace('-','/')} · {e.label}</button>)}</div></section><DayPanel mobile={mobile} day={selected} open={dayOpen} onClose={()=>setDayOpen(false)}><div className="day-heading"><div className="detail-title"><div><span className="eyebrow">{selected.slice(0,4)} · 这一天的故事</span><h2 id="day-title">{pretty(selected)}</h2></div><button type="button" className="sheet-close" onClick={()=>setDayOpen(false)} aria-label="关闭当天记录">×</button></div><div className="day-navigation"><button type="button" disabled={selected==='1900-01-01'} onClick={()=>stepDay(-1)} aria-label="前一天">← 前一天</button><span>{byDay[selected]?.count||0} 段回忆</span><button type="button" disabled={selected==='2200-12-31'} onClick={()=>stepDay(1)} aria-label="后一天">后一天 →</button></div></div><div className="selected-occasions">{selectedEvents.map(e=><div key={e.id}><span aria-hidden="true">{e.kind==='birthday'?'🎂':'♥'}</span><strong>{e.label}</strong><small>{e.day===today?'今天值得好好庆祝':e.day>today?`距离这一天还有 ${daysBetween(today,e.day)} 天`:'值得珍藏的一天'}</small></div>)}</div><button className="add-day" onClick={()=>{setFiles([]);setPostTags([]);setLocation(null);setError('');setDayOpen(false);setCompose(true)}}>＋ 为这一天添加回忆</button>{dayError?<p className="error" role="alert">{dayError} <button type="button" onClick={()=>refresh().catch(()=>{})}>重新加载</button></p>:null}{(loadedDay!==selected||dayLoading||dayError)&&!daily.length?<p role="status">{dayError?'当天记录暂未加载。':'正在加载当天记录…'}</p>:!daily.length?<div className="empty"><div>☁</div><h3>这一天，还留着空白</h3><p>一张照片，一句想说的话，<br/>都可以成为回忆的开始。</p></div>:daily.map(e=><EntryCard key={e.id} entry={e} me={me} refresh={refresh} onEdit={setEditing} onDelete={remove} onGallery={setGallery}/>)}</DayPanel></div>{mobile&&summary}<div className="bottom"><span>日子不必特别，有你就值得记录。</span><a href="/api/export">导出文字与记录清单</a></div></main>{compose&&<div className="overlay"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="compose-title"><div className="detail-title"><h2 id="compose-title">收藏一个小日子</h2><button disabled={saving||tagBusy||liveDetecting} onClick={()=>setCompose(false)} aria-label="关闭">×</button></div><form onSubmit={save}><label>记录日期<input type="date" name="day" defaultValue={selected} disabled={saving} required min="1900-01-01" max="2200-12-31"/></label><label>今天想记住什么？<textarea autoFocus name="body" disabled={saving} rows="4" maxLength={5000} placeholder="今天一起吃了喜欢的晚饭，也聊了好多没头没尾的话……"/></label><LocationPicker value={location} onChange={setLocation} disabled={saving} request={api}/><TagPicker value={postTags} onChange={setPostTags} disabled={saving} onBusyChange={setTagBusy} request={api}/><label className="upload">＋ 添加照片或视频<input type="file" name="files" multiple accept="image/*,video/*" disabled={saving} onChange={e=>{if(e.target.files.length)setFiles(Array.from(e.target.files));e.target.value=''}}/><small>最多 12 个 · 单个 100 MB · 合计 200 MB</small></label><label className="upload">从文件导入实况（.livp / 照片＋视频）<input type="file" multiple disabled={saving} onChange={e=>{if(e.target.files.length)setFiles(Array.from(e.target.files));e.target.value=''}}/><small>选择完整 .livp，或同时选择同名 HEIC/JPG 与 MOV/MP4；重新选择会替换当前附件。</small></label><LiveUploads files={files} value={liveOptions} onChange={setLiveOptions} onBusyChange={setLiveDetecting} disabled={saving}/><p className="hint">iPhone 相册若无法选择，请用“从文件导入实况”。相册只传来静态照片时，可在苹果照片中“存储为视频”，再补选该视频。</p>{error&&<p className="error" role="alert">{error}</p>}{saving&&<p role="status">{progress===100?'已上传，正在处理照片和实况，请稍候…':`正在上传 ${progress}%`}</p>}<button className="primary" disabled={saving||tagBusy||liveDetecting}>{saving?'正在保存…':'保存到我们的日历'}</button></form></section></div>}{editing&&<EditEntry entry={editing} onClose={()=>setEditing(null)} onSaved={async day=>{setEditing(null);setSelected(day);const d=new Date(day+'T12:00:00');setMonth(new Date(d.getFullYear(),d.getMonth(),1));try{await refresh()}catch{setError('修改已保存，请刷新页面查看。')}}}/>}{gallery&&<PhotoViewer photos={gallery.photos} initialIndex={gallery.index} onClose={()=>setGallery(null)}/>}{monthlyOpen&&<MonthlyMemories key={me.id} me={me} onClose={()=>setMonthlyOpen(false)} onVisit={visitActivity}/>}</EmojiContext.Provider></CommentDrafts>;
}
createRoot(document.getElementById('root')).render(<App/>);
