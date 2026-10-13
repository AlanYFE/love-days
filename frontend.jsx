import React, {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {createPortal} from 'react-dom';
import './noop.js';
import TagPicker from './tags.jsx';
import {LiveUploads,LivePhoto} from './live-photos.jsx';
const now=new Date();
const localDay=(d)=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const today=localDay(now), level=n=>n===0?0:n===1?1:n<=3?2:n<=6?3:4;
const pretty=d=>new Date(d+'T12:00:00').toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'});
async function api(path,options={}){const r=await fetch(path,{...options,headers:{'X-Blue-Request':'1',...options.headers}});let data;try{data=await r.json()}catch{throw Error('服务暂时不可用，请稍后重试')}if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'请求失败，请检查输入');return data}
const EmojiContext=React.createContext({emojis:[],reloadEmojis:async()=>{}});
function EmojiPicker({onSelect,label='☺ 表情',disabled=false}){
 const {emojis,reloadEmojis}=React.useContext(EmojiContext);
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[name,setName]=useState('');
 const trigger=React.useRef(null);
 function close(){if(busy)return;setOpen(false);trigger.current?.focus()}
 useEffect(()=>{if(!open)return;const key=e=>{if(e.key==='Escape'&&!busy){setOpen(false);trigger.current?.focus()}};document.addEventListener('keydown',key);return()=>document.removeEventListener('keydown',key)},[open,busy]);
 async function upload(event){
  const file=event.target.files?.[0];event.target.value='';if(!file)return;
  if(file.size>5*1024*1024){setError('表情图片不能超过 5 MB');return}
  const data=new FormData();data.append('file',file);data.append('name',name.trim()||file.name.replace(/\.[^.]+$/,'').slice(0,24)||'小表情');
  setBusy(true);setError('');
  try{await api('/api/emojis',{method:'POST',body:data});setName('');try{await reloadEmojis()}catch{setError('表情已上传，请关闭并重新打开表情库查看。')}}catch(e){setError(e.message)}finally{setBusy(false)}
 }
 return <><button type="button" ref={trigger} className="emoji-trigger" disabled={disabled} aria-haspopup="dialog" aria-expanded={open} onClick={()=>{setOpen(true);setError('');reloadEmojis().catch(e=>setError(e.message))}}>{label}</button>{open&&createPortal(<div className="emoji-overlay" onClick={e=>{if(e.target===e.currentTarget)close()}}><section className="emoji-picker" role="dialog" aria-modal="true" aria-label="我们的表情库"><div className="detail-title"><div><h2>我们的表情库</h2><p>你上传的表情，对方也能使用。</p></div><button type="button" autoFocus disabled={busy} onClick={close} aria-label="关闭表情库">×</button></div><div className="emoji-grid">{emojis.map(emoji=>onSelect?<button type="button" key={emoji.id} title={emoji.name} disabled={busy} onClick={()=>{onSelect(emoji);close()}}><img loading="lazy" src={emoji.url} alt={emoji.name}/><span>{emoji.name}</span></button>:<a key={emoji.id} href={emoji.url} target="_blank" rel="noreferrer" title={emoji.name}><img loading="lazy" src={emoji.url} alt={emoji.name}/><span>{emoji.name}</span></a>)}</div>{!emojis.length&&<p className="emoji-empty">还没有表情，上传第一张喜欢的图片吧。</p>}<div className="emoji-upload"><label>表情名称（可选）<input value={name} maxLength={24} disabled={busy} onChange={e=>setName(e.target.value)} placeholder="例如：抱抱、好耶"/></label><label className="emoji-upload-button">{busy?'正在上传…':'＋ 上传图片 / GIF'}<input type="file" disabled={busy} accept="image/jpeg,image/png,image/webp,image/gif" onChange={upload}/></label><p className="hint">单个 ≤ 5 MB · 最长边 2048 像素 · 动画 ≤ 200 帧<br/>共享库 {emojis.length}/100；GIF 保留动画。</p></div>{error&&<p className="error" role="alert">{error}</p>}</section></div>,document.body)}</>;
}
function Reactions({kind,target,me,refresh}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const reactions=target.reactions||[];
 async function choose(emoji){
  if(busy)return;const existing=reactions.find(r=>r.emoji.id===emoji.id);const active=!existing?.user_ids.includes(me.id);
  setBusy(true);setError('');
  try{await api(`/api/${kind}/${target.id}/reactions/${emoji.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({active})});try{await refresh()}catch{setError('回应已保存，请刷新页面查看。')}}catch(e){setError(e.message)}finally{setBusy(false)}
 }
 return <div className="reaction-section"><div className="reaction-row">{reactions.map(r=><button type="button" className={'reaction-chip '+(r.user_ids.includes(me.id)?'mine':'')} key={r.emoji.id} aria-pressed={r.user_ids.includes(me.id)} aria-label={`${r.emoji.name}，${r.count} 人回应${r.user_ids.includes(me.id)?'，点击取消':'，点击加入'}`} title={r.emoji.name} disabled={busy} onClick={()=>choose(r.emoji)}><img src={r.emoji.url} alt="" loading="lazy"/><span>{r.count}</span></button>)}<EmojiPicker onSelect={choose} disabled={busy} label="☺ ＋"/></div>{error&&<p role="alert" className="error">{error}</p>}</div>;
}

function Comments({entry, me, refresh}) {
 const [draft,setDraft]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [chosen,setChosen]=useState([]);
 const comments=entry.comments||[];
 async function submit(event){
  event.preventDefault();if(busy||(!draft.trim()&&!chosen.length))return;
  setBusy(true);setError('');
  try{
   await api('/api/entries/'+entry.id+'/comments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({body:draft,emoji_ids:chosen.map(e=>e.id)})});
   setDraft('');setChosen([]);
   try{await refresh()}catch{setError('评论已保存，列表刷新失败，请刷新页面查看。')}
  }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 async function remove(comment){
  if(busy||!confirm('确定删除自己的这条评论？'))return;
  setBusy(true);setError('');
  try{await api('/api/comments/'+comment.id,{method:'DELETE'});await refresh()}
  catch(e){setError(e.message)}finally{setBusy(false)}
 }
 return <section className="comments" aria-label="帖子评论">
  <h3>留言 <span>{comments.length}</span></h3>
  {!comments.length&&<p className="comment-empty">给这个小日子留句话吧。</p>}
  <div className="comment-list">{comments.map(c=><div className="comment" key={c.id}>
   <div className="comment-meta"><strong>{c.author}</strong><time dateTime={new Date(c.created*1000).toISOString()}>{new Date(c.created*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})}</time>{c.user_id===me.id&&<button type="button" className="textbtn" disabled={busy} onClick={()=>remove(c)} aria-label={'删除'+c.author+'的这条评论'}>删除</button>}</div>
   {c.body&&<p className="comment-body">{c.body}</p>}
   {!!c.emojis?.length&&<div className="comment-stickers">{c.emojis.map((emoji,i)=><a key={i} href={emoji.url} target="_blank" rel="noreferrer"><img src={emoji.url} loading="lazy" alt={emoji.name} title={emoji.name}/></a>)}</div>}
   <Reactions kind="comments" target={c} me={me} refresh={refresh}/>
  </div>)}</div>
  <form className="comment-form" onSubmit={submit}>
   <textarea aria-label="评论内容" placeholder="想对你说……" rows="2" maxLength={1000} value={draft} disabled={busy} onChange={e=>setDraft(e.target.value)}/>
   {!!chosen.length&&<div className="chosen-emojis">{chosen.map((emoji,i)=><button key={i} type="button" disabled={busy} onClick={()=>setChosen(items=>items.filter((_,j)=>j!==i))} aria-label={'移除'+emoji.name}><img src={emoji.url} alt={emoji.name}/><span>×</span></button>)}</div>}
   <div className="comment-actions"><EmojiPicker disabled={busy||chosen.length>=8} onSelect={emoji=>setChosen(items=>items.length<8?[...items,emoji]:items)}/><span>{draft.length}/1000 · {chosen.length}/8</span><button className="primary" disabled={busy||(!draft.trim()&&!chosen.length)}>{busy?'处理中…':'发送留言'}</button></div>
  </form>
  {error&&<p role="alert" className="error">{error}</p>}
 </section>;
}

function MonthSelector({month,view,onChange}){
 const dialog=React.useRef(null);
 const [year,setYear]=useState(month.getFullYear()),[selectedMonth,setSelectedMonth]=useState(month.getMonth());
 function open(){setYear(month.getFullYear());setSelectedMonth(month.getMonth());dialog.current.showModal()}
 function jump(event){event.preventDefault();onChange(new Date(year,selectedMonth,1));dialog.current.close()}
 function current(){const d=new Date();onChange(new Date(d.getFullYear(),d.getMonth(),1));dialog.current.close()}
 return <><button type="button" className="month-title" aria-haspopup="dialog" aria-label="选择年份和月份" title="点击选择年份和月份" onClick={open}>{month.getFullYear()} 年{view==='month'?` ${month.getMonth()+1} 月`:''}<span aria-hidden="true">⌄</span></button>
 <dialog ref={dialog} className="month-dialog" aria-labelledby="month-dialog-title" onClick={e=>{if(e.target===dialog.current){const r=dialog.current.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.current.close()}}}>
  <div className="detail-title"><h2 id="month-dialog-title">跳到某个日子</h2><button type="button" className="month-close" aria-label="关闭年月选择" onClick={()=>dialog.current.close()}>×</button></div>
  <p>选好年份和月份，去看看那时的我们。</p>
  <form onSubmit={jump}><div className="month-fields"><label>年份<select value={year} onChange={e=>setYear(Number(e.target.value))}>{Array.from({length:301},(_,i)=>1900+i).map(y=><option key={y} value={y}>{y} 年</option>)}</select></label><label>月份<select value={selectedMonth} onChange={e=>setSelectedMonth(Number(e.target.value))}>{Array.from({length:12},(_,i)=><option key={i} value={i}>{i+1} 月</option>)}</select></label></div>
  <div className="month-dialog-actions"><button type="button" className="textbtn" onClick={current}>回到本月</button><button type="submit" className="primary">跳转</button></div></form>
 </dialog></>;
}

function PhotoViewer({photos,initialIndex,onClose}){
 const dialog=React.useRef(null),touch=React.useRef(null);
 const [index,setIndex]=useState(initialIndex),[status,setStatus]=useState('loading');
 const photo=photos[index];
 function move(delta){setIndex(i=>(i+delta+photos.length)%photos.length)}
 useEffect(()=>{
  const node=dialog.current,previous=document.activeElement,overflow=document.body.style.overflow;
  node.showModal();document.body.style.overflow='hidden';
  return()=>{node.close();document.body.style.overflow=overflow;if(previous?.isConnected)previous.focus({preventScroll:true})};
 },[]);
 useEffect(()=>{setStatus('loading')},[index]);
 return createPortal(<dialog ref={dialog} className="photo-viewer" aria-label="照片预览" onCancel={e=>{e.preventDefault();onClose()}} onKeyDown={e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();move(e.key==='ArrowLeft'?-1:1)}}}>
  <div className="photo-toolbar"><span aria-live="polite">{index+1} / {photos.length}</span><button type="button" autoFocus onClick={onClose} aria-label="关闭照片预览">×</button></div>
  <div className="photo-stage" onClick={e=>{if(e.target===e.currentTarget)onClose()}} onTouchStart={e=>{touch.current=e.touches.length===1?{x:e.touches[0].clientX,y:e.touches[0].clientY}:null}} onTouchCancel={()=>{touch.current=null}} onTouchEnd={e=>{const start=touch.current;touch.current=null;if(!start||!e.changedTouches.length)return;const dx=e.changedTouches[0].clientX-start.x,dy=e.changedTouches[0].clientY-start.y;if(Math.abs(dx)>60&&Math.abs(dx)>Math.abs(dy)*1.5)move(dx<0?1:-1)}}>
   {status==='loading'&&<span className="photo-status" role="status">正在加载照片…</span>}
   {status==='error'&&<span className="photo-status" role="alert">照片加载失败，请关闭后重试。</span>}
   {photo.live?<LivePhoto key={photo.id} photo={photo} onBackground={onClose} onLoad={()=>setStatus('ready')} onError={()=>setStatus('error')}/>:<img key={photo.id} src={photo.url} alt={`帖子照片 ${index+1}`} draggable="false" onLoad={()=>setStatus('ready')} onError={()=>setStatus('error')}/>}
  </div>
  {photos.length>1&&<><button type="button" className="photo-prev" onClick={()=>move(-1)} aria-label="上一张照片">‹</button><button type="button" className="photo-next" onClick={()=>move(1)} aria-label="下一张照片">›</button></>}
  <p className="photo-help">{photos.length>1?'左右切换 · 手机可滑动 · ':''}点击背景关闭</p>
 </dialog>,document.body);
}

function EditEntry({entry,onClose,onSaved}){
 const [chosenTags,setChosenTags]=useState(entry.tags||[]),[tagBusy,setTagBusy]=useState(false);
 const dialog=React.useRef(null);
 const [day,setDay]=useState(entry.day),[body,setBody]=useState(entry.body),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{const node=dialog.current,previous=document.activeElement,overflow=document.body.style.overflow;node.showModal();document.body.style.overflow='hidden';return()=>{node.close();document.body.style.overflow=overflow;if(previous?.isConnected)previous.focus({preventScroll:true})}},[]);
 function close(){if(busy||tagBusy)return;if((day!==entry.day||body!==entry.body||JSON.stringify(chosenTags.map(t=>t.id).sort())!==JSON.stringify((entry.tags||[]).map(t=>t.id).sort()))&&!confirm('放弃尚未保存的修改？'))return;onClose()}
 async function submit(event){event.preventDefault();if(busy||tagBusy)return;setBusy(true);setError('');try{await api('/api/entries/'+entry.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({day,body,tag_ids:chosenTags.map(t=>t.id),original:{day:entry.day,body:entry.body,tag_ids:(entry.tags||[]).map(t=>t.id)}})})}catch(e){setError(e.message);setBusy(false);return}onSaved(day)}
 return createPortal(<dialog ref={dialog} className="edit-dialog" aria-labelledby="edit-title" onCancel={e=>{e.preventDefault();close()}}>
  <div className="detail-title"><h2 id="edit-title">编辑这一天的回忆</h2><button type="button" disabled={busy||tagBusy} onClick={close} aria-label="关闭编辑">×</button></div>
  <form onSubmit={submit}><label>记录日期<input type="date" required min="1900-01-01" max="2200-12-31" value={day} disabled={busy} onChange={e=>setDay(e.target.value)}/></label><label>今天想记住什么？<textarea autoFocus rows="6" maxLength={5000} value={body} disabled={busy} onChange={e=>setBody(e.target.value)}/></label><p className="hint">{body.length}/5000 字 · 可修改文字、日期和标签，原有照片、视频及留言会保留。</p><TagPicker value={chosenTags} onChange={setChosenTags} disabled={busy} onBusyChange={setTagBusy} request={api}/>{error&&<p className="error" role="alert">{error}</p>}<div className="edit-actions"><button type="button" className="textbtn" disabled={busy||tagBusy} onClick={close}>取消</button><button className="primary" disabled={busy||tagBusy||(!body.trim()&&!entry.media.length)}>{busy?'正在保存…':'保存修改'}</button></div></form>
 </dialog>,document.body);
}

function App(){
 const [liveOptions,setLiveOptions]=useState([]),[liveDetecting,setLiveDetecting]=useState(false);
 const [postTags,setPostTags]=useState([]),[tagBusy,setTagBusy]=useState(false);
 const [editing,setEditing]=useState(null);
 const [gallery,setGallery]=useState(null);
 const [emojis,setEmojis]=useState([]);
 async function reloadEmojis(){setEmojis(await api('/api/emojis'))}
 const [me,setMe]=useState(null),[loading,setLoading]=useState(true),[entries,setEntries]=useState([]),[error,setError]=useState('');
 const [month,setMonth]=useState(new Date(now.getFullYear(),now.getMonth(),1)),[view,setView]=useState('month'),[selected,setSelected]=useState(today),[compose,setCompose]=useState(false),[saving,setSaving]=useState(false),[progress,setProgress]=useState(0),[files,setFiles]=useState([]);
 async function refresh(){setEntries(await api('/api/entries'))}
 useEffect(()=>{if(me)reloadEmojis().catch(e=>setError(e.message));else setEmojis([])},[me]);
 useEffect(()=>{api('/api/me').then(async u=>{setMe(u);await refresh()}).catch(e=>{if(e.message!=='请先登录')setError(e.message)}).finally(()=>setLoading(false))},[]);
 useEffect(()=>{if(!me)return;const id=setInterval(()=>refresh().catch(()=>{}),30000);return()=>clearInterval(id)},[me]);
 async function login(e){e.preventDefault();setError('');const f=new FormData(e.target);try{setSaving(true);setMe(await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(f))}));await refresh()}catch(e){setError(e.message)}finally{setSaving(false)}}
 const byDay={};for(const e of entries)(byDay[e.day]??=[]).push(e);
 const daily=byDay[selected]||[],y=month.getFullYear(),m=month.getMonth();
 const prefix=view==='month'?`${y}-${String(m+1).padStart(2,'0')}`:String(y);
 const scoped=entries.filter(e=>e.day.startsWith(prefix));
 function cover(day){return (byDay[day]||[]).flatMap(e=>e.media).find(x=>x.thumb)}
 function shift(n){const d=new Date(y+(view==='year'?n:0),m+(view==='month'?n:0),1);if(d.getFullYear()>=1900&&d.getFullYear()<=2200)setMonth(d)}
 function dayButton(d,mini=false){const ds=localDay(d),n=(byDay[ds]||[]).length,c=cover(ds);return <button key={ds} className={`day l${level(n)} ${ds===selected?'selected':''} ${ds===today?'today':''} ${mini?'mini':''}`} onClick={()=>{setSelected(ds);if(mini)document.querySelector('#day-detail')?.scrollIntoView({behavior:'smooth',block:'start'})}} title={`${ds} · ${n} 条记录`} aria-label={`${ds}，${n} 条记录`} aria-pressed={ds===selected}>{c&&<img src={c.thumb} loading="lazy" alt=""/>}{!mini&&<><span className="daynum">{d.getDate()}</span>{c?.kind==='video'&&<span className="play">▷</span>}{n>0&&<span className="daycount">{n}<span className="countlabel"> 条</span></span>}{!c&&n>0&&<span className="excerpt">{byDay[ds][0].body||'一段小回忆'}</span>}</>}</button>}
 async function remove(e){if(!confirm('确定删除这条记录、附件及其下所有评论？此操作无法撤销。'))return;try{await api('/api/entries/'+e.id,{method:'DELETE'});await refresh()}catch(e){setError(e.message)}}
 function save(e){e.preventDefault();if(saving||tagBusy||liveDetecting)return;setError('');const form=new FormData(e.target);form.set('tag_ids',JSON.stringify(postTags.map(t=>t.id)));const allFiles=[...files,...liveOptions.filter(o=>o.enabled&&o.pair).map(o=>o.pair)];if(files.length>12||allFiles.some(f=>f.size>100*1024*1024)||allFiles.reduce((n,f)=>n+f.size,0)>200*1024*1024){setError('最多 12 个附件；单个 100 MB，合计 200 MB。');return}form.delete('files');files.forEach(f=>form.append('files',f));form.set('live_options',JSON.stringify(files.map((f,i)=>({enabled:!!liveOptions[i]?.enabled,paired:!!(liveOptions[i]?.enabled&&liveOptions[i]?.pair)}))));liveOptions.forEach((o,i)=>{if(o.enabled&&o.pair)form.append('live_'+i,o.pair)});setSaving(true);setProgress(0);const xhr=new XMLHttpRequest();xhr.open('POST','/api/entries');xhr.setRequestHeader('X-Blue-Request','1');xhr.upload.onprogress=e=>{if(e.lengthComputable)setProgress(Math.round(e.loaded/e.total*100))};xhr.onerror=()=>{setSaving(false);setError('网络连接中断，请检查当天记录后重试，避免重复发布。')};xhr.onload=async()=>{try{let data;try{data=JSON.parse(xhr.responseText)}catch{throw Error('上传失败，可能超过服务器限制')}if(xhr.status>=400)throw Error(typeof data.detail==='string'?data.detail:'上传失败');setSelected(form.get('day'));const d=new Date(form.get('day')+'T12:00:00');setMonth(new Date(d.getFullYear(),d.getMonth(),1));setCompose(false);setFiles([]);await refresh()}catch(e){setError(e.message)}finally{setSaving(false)}};xhr.send(form)}
 if(loading)return <div className="loading">正在打开我们的日历…</div>;
 if(!me)return <main className="login"><div className="login-art"><div className="brand">◈ LOVE DAYS</div><h1>把平凡的日子，<br/>慢慢染成蓝色。</h1><p>两个人，一本日历。<br/>照片、心情，还有那些值得记住的小事。</p><div className="art-grid" aria-hidden="true">{Array.from({length:77},(_,i)=><i key={i} className={'l'+([0,1,2,3,4,0,2,1,3,0,4][i%11])}/>)}</div><small>OUR LITTLE CORNER OF THE WORLD</small></div><section className="login-form"><span className="eyebrow">ONLY US · 两个人的空间</span><h2>欢迎回家</h2><p>用你的账号，打开属于我们的每一天。</p><form onSubmit={login}><label>账号<input required name="username" autoComplete="username" placeholder="你的登录账号" maxLength={100}/></label><label>密码<input required type="password" name="password" autoComplete="current-password" placeholder="输入密码" maxLength={256}/></label>{error&&<p role="alert" className="error">{error}</p>}<button className="primary" disabled={saving}>{saving?'正在登录…':'打开我们的日历 →'}</button></form><small>仅限两位成员登录 · 照片和记录不公开</small></section></main>;
 const calendar=[];const first=(new Date(y,m,1).getDay()+6)%7;for(let i=0;i<first;i++)calendar.push(<div key={'blank'+i}/>);for(let d=1;d<=new Date(y,m+1,0).getDate();d++)calendar.push(dayButton(new Date(y,m,d)));
 const yearDays=[];for(let i=0;i<(new Date(y,0,1).getDay()+6)%7;i++)yearDays.push(<i key={'pad'+i}/>);for(let d=new Date(y,0,1);d.getFullYear()===y;d.setDate(d.getDate()+1))yearDays.push(dayButton(new Date(d),true));
 return <EmojiContext.Provider value={{emojis,reloadEmojis}}><header><a className="brand" href="/">◈ Love Days <small>OUR SHARED DIARY</small></a><div className="account"><span className="avatar">{me.name.slice(0,1)}</span><span>{me.name}</span><button className="textbtn" onClick={async()=>{try{await api('/api/logout',{method:'POST'});setMe(null);setEntries([])}catch(e){setError(e.message)}}}>退出</button></div></header><main className="shell"><section className="intro"><div><span className="eyebrow">A LITTLE MORE BLUE, A LITTLE MORE US</span><h1>我们的每一天<span>。</span></h1><p>把一起走过的日子，收藏在这里。</p></div><div className="intro-actions"><EmojiPicker label="☺ 表情库"/><button className="primary" onClick={()=>{setSelected(today);setFiles([]);setPostTags([]);setCompose(true);setError('')}}>＋ 记下今天</button></div></section><section className="stats"><div><strong>{new Set(entries.map(e=>e.day)).size}</strong><span>个有回忆的日子</span></div><div><strong>{entries.length}</strong><span>条共同收藏</span></div><div><strong>{entries.reduce((n,e)=>n+e.media.length,0)}</strong><span>张照片与段视频</span></div><div className="stats-note">日子不必特别，<br/>有你就值得记录。</div></section>{error&&!compose&&<p role="alert" className="error">{error}</p>}<div className="workspace"><section className="calendar panel"><div className="calendar-toolbar"><div className="month-nav"><button onClick={()=>shift(-1)} aria-label="上一页">‹</button><MonthSelector month={month} view={view} onChange={d=>{setMonth(d);setSelected(localDay(d))}}/><button onClick={()=>shift(1)} aria-label="下一页">›</button></div><div className="tabs"><button className={view==='month'?'active':''} onClick={()=>setView('month')}>照片月历</button><button className={view==='year'?'active':''} onClick={()=>setView('year')}>全年热力图</button></div></div>{view==='month'?<><div className="weekdays">{'一二三四五六日'.split('').map(d=><span key={d}>{d}</span>)}</div><div className="month-grid">{calendar}</div></>:<><p className="muted">每一格是一天 · 从左到右为每周，周一在上</p><div className="year-scroll"><div className="year-grid">{yearDays}</div></div></>}<footer className="legend"><span>{view==='month'?'本月':'本年'} {scoped.length} 条记录</span><div>少 {[0,1,2,3,4].map(x=><i key={x} className={'l'+x} title={['0','1','2–3','4–6','7+'][x]+' 条'}/>)} 多</div></footer><p className="hint">每发布一条记录，蓝色加深一点。点击日期，打开当天的回忆。</p></section><aside className="panel detail" id="day-detail"><div className="detail-title"><div><span className="eyebrow">DAILY MEMORIES</span><h2>{pretty(selected)}</h2></div><span className="badge">{daily.length} 条</span></div><button className="add-day" onClick={()=>{setFiles([]);setPostTags([]);setError('');setCompose(true)}}>＋ 为这一天添加回忆</button>{!daily.length?<div className="empty"><div>☁</div><h3>这一天，还留着空白</h3><p>一张照片，一句想说的话，<br/>都可以成为回忆的开始。</p></div>:daily.map(e=><article className="entry" key={e.id}><div className="entry-meta"><span className="avatar">{e.author.slice(0,1)}</span><strong>{e.author}</strong><time>{new Date(e.created*1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}</time></div>{e.body&&<p className="entry-body">{e.body}</p>}<div className="entry-tags" aria-label="帖子标签">{(e.tags||[]).map(tag=><span className="tag-chip" key={tag.id}># {tag.name}</span>)}</div><div className="attachments">{e.media.map(a=>a.kind==='image'?<button type="button" className="photo-open" key={a.id} aria-label={a.live?"放大查看实况照片":"放大查看照片"} onClick={()=>{const photos=e.media.filter(item=>item.kind==='image');setGallery({photos,index:photos.findIndex(item=>item.id===a.id)})}}><img src={a.thumb||a.url} alt="当天的照片，点击放大" loading="lazy"/>{a.live&&<span className="live-badge">◎ LIVE</span>}</button>:<video key={a.id} controls preload="none" playsInline poster={a.thumb||undefined} src={a.url}/>)}</div>{e.user_id===me.id&&<div className="entry-actions"><button type="button" className="textbtn" onClick={()=>setEditing(e)}>编辑</button><button type="button" className="textbtn delete" onClick={()=>remove(e)}>删除这条记录</button></div>}<Reactions kind="entries" target={e} me={me} refresh={refresh}/><Comments entry={e} me={me} refresh={refresh}/></article>)}</aside></div><div className="bottom"><span>ONLY US. ALWAYS.</span><a href="/api/export">导出文字与记录清单</a></div></main>{compose&&<div className="overlay"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="compose-title"><div className="detail-title"><h2 id="compose-title">收藏一个小日子</h2><button disabled={saving||tagBusy||liveDetecting} onClick={()=>setCompose(false)} aria-label="关闭">×</button></div><form onSubmit={save}><label>记录日期<input type="date" name="day" defaultValue={selected} required min="1900-01-01" max="2200-12-31"/></label><label>今天想记住什么？<textarea autoFocus name="body" rows="4" maxLength={5000} placeholder="今天一起吃了喜欢的晚饭，也聊了好多没头没尾的话……"/></label><TagPicker value={postTags} onChange={setPostTags} disabled={saving} onBusyChange={setTagBusy} request={api}/><label className="upload">＋ 添加照片或视频<input type="file" name="files" multiple accept="image/jpeg,image/png,image/webp,image/gif,image/heic,image/heif,video/mp4,video/quicktime,.heic,.heif,.mov" disabled={saving} onChange={e=>setFiles(Array.from(e.target.files))}/><small>最多 12 个 · 单个 100 MB · 合计 200 MB</small></label><LiveUploads files={files} value={liveOptions} onChange={setLiveOptions} onBusyChange={setLiveDetecting} disabled={saving}/><p className="hint">支持 HEIC 照片。iPhone 网页选图可能不携带动态视频；补选视频后可合成实况播放。</p>{error&&<p className="error" role="alert">{error}</p>}{saving&&<p role="status">{progress===100?'已上传，正在处理照片和实况，请稍候…':`正在上传 ${progress}%`}</p>}<button className="primary" disabled={saving||tagBusy||liveDetecting}>{saving?'正在保存…':'保存到我们的日历'}</button></form></section></div>}{editing&&<EditEntry entry={editing} onClose={()=>setEditing(null)} onSaved={async day=>{setEditing(null);setSelected(day);const d=new Date(day+'T12:00:00');setMonth(new Date(d.getFullYear(),d.getMonth(),1));try{await refresh()}catch{setError('修改已保存，请刷新页面查看。')}}}/>}{gallery&&<PhotoViewer photos={gallery.photos} initialIndex={gallery.index} onClose={()=>setGallery(null)}/>}</EmojiContext.Provider>;
}
createRoot(document.getElementById('root')).render(<App/>);
