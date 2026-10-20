import React,{useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {api} from './api.mjs';
import {chinaToday} from './anniversaries.mjs';

export default function MonthlyMemories({me,onClose,onVisit}){
 const dialog=useRef(null);
 const [month,setMonth]=useState(chinaToday().slice(0,7)),[data,setData]=useState(null),[selected,setSelected]=useState([]);
 const [editor,setEditor]=useState(null),[original,setOriginal]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const dirty=editor&&JSON.stringify(editor)!==original;
 useEffect(()=>{const node=dialog.current,previous=document.activeElement,overflow=document.body.style.overflow;node.showModal();document.body.style.overflow='hidden';return()=>{node.close();document.body.style.overflow=overflow;previous?.isConnected&&previous.focus({preventScroll:true})}},[]);
 useEffect(()=>{let active=true;setData(null);setEditor(null);setError('');setNotice('');api('/api/monthly/'+month).then(d=>{if(active){setData(d);setSelected(d.entries.map(e=>e.id))}}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[month]);
 function close(){if(busy)return;if(dirty&&!confirm('放弃尚未保存的回忆修改？'))return;onClose()}
 function open(memory){if(dirty&&!confirm('放弃尚未保存的回忆修改？'))return;const e={...memory,...memory.payload,note:memory.payload.notes[me.id]?.text||''};setEditor(e);setOriginal(JSON.stringify(e));setError('');setNotice('')}
 async function reload(){const d=await api('/api/monthly/'+month);setData(d);return d}
 async function create(){if(busy)return;if(dirty&&!confirm('放弃尚未保存的修改，创建另一份草稿？'))return;setBusy(true);setError('');try{const m=await api('/api/monthly/'+month,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({entry_ids:selected})});const e={...m,...m.payload,note:''};setEditor(e);setOriginal(JSON.stringify(e));setNotice('已创建手动草稿；尚未调用 AI。');await reload()}catch(e){setError(e.message)}finally{setBusy(false)}}
 function change(key,value){setEditor(e=>({...e,[key]:value}));setNotice('')}
 async function save(status){if(busy)return;setBusy(true);setError('');try{const m=await api(`/api/monthly/${month}/${editor.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:editor.revision,title:editor.title,body:editor.body,note:editor.note,cover_id:editor.cover_id,highlights:editor.highlights,status})});const e={...m,...m.payload,note:m.payload.notes[me.id]?.text||''};setEditor(e);setOriginal(JSON.stringify(e));setNotice(status==='saved'?'已收藏，你们两个人都能查看。':'草稿已保存。');await reload()}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function visit(entry){if(busy)return;if(dirty&&!confirm('放弃尚未保存的修改，查看原帖？'))return;setBusy(true);setError('');try{const focus=await onVisit({entry_id:entry.id});onClose();requestAnimationFrame(()=>requestAnimationFrame(()=>focus?.()))}catch(e){setError(e.message)}finally{setBusy(false)}}
 const chosen=data?.entries.filter(e=>selected.includes(e.id))||[];
 const source=data?.entries.filter(e=>editor?.entry_ids.includes(e.id))||[];
 const photos=source.flatMap(e=>e.media.filter(m=>m.kind==='image').map(m=>({...m,day:e.day})));
 const cover=photos.find(p=>p.id===editor?.cover_id);
 return createPortal(<dialog ref={dialog} className="monthly-dialog" aria-labelledby="monthly-title" onCancel={e=>{e.preventDefault();close()}}>
  <div className="detail-title"><div><span className="eyebrow">OUR MONTHLY MEMORIES</span><h2 id="monthly-title">我们的月度回忆</h2></div><button type="button" disabled={busy} onClick={close} aria-label="关闭月度回忆">×</button></div>
  <label>选择月份<input type="month" value={month} min="1900-01" max="2200-12" disabled={busy} onChange={e=>{const v=e.target.value;if(!/^(19\d{2}|20\d{2}|21\d{2}|2200)-(0[1-9]|1[0-2])$/.test(v))return;if(dirty&&!confirm('放弃尚未保存的修改，切换月份？'))return;setMonth(v)}}/></label>
  <p className="monthly-info">先把回忆整理好。AI 服务商尚未配置，目前支持手动编辑与收藏，不会发送照片、正文或评论到外部。</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p role="status" className="monthly-info">{notice}</p>}
  {!data?<p role="status">{error?'加载失败，请关闭后重新打开。':'正在读取这个月的回忆…'}</p>:<>
   <p className="hint">{month===data.as_of.slice(0,7)?`当月记录截至 ${data.as_of}`:'统计来自该月已有记录'} · {data.stats.days} 天 · {data.stats.posts} 条帖子 · {data.stats.photos} 张照片 · {data.stats.videos} 段视频 · {data.stats.comments} 条留言</p>
   {!!data.stats.tags.length&&<div className="entry-tags">{data.stats.tags.map(t=><span className="tag-chip" key={t.name}>#{t.name} · {t.count} 次</span>)}</div>}
   <div className="monthly-layout"><section className="monthly-sources"><h3>选择回忆素材</h3><p className="hint">选中 {chosen.length} 条记录。每份草稿独立保存，不覆盖已收藏的版本。</p>
    <div className="monthly-source-list">{data.entries.map(e=><label className="monthly-source" key={e.id}><input type="checkbox" disabled={busy} checked={selected.includes(e.id)} onChange={event=>setSelected(s=>event.target.checked?[...s,e.id]:s.filter(id=>id!==e.id))}/><span><strong>{e.day} · {e.author}</strong><small>{e.body.slice(0,100)||'一段影像回忆'}</small><small>{e.media.length} 个附件 · {e.comments.length} 条留言</small></span>{e.media.find(m=>m.thumb)&&<img src={e.media.find(m=>m.thumb).thumb} alt="帖子缩略图" loading="lazy"/>}</label>)}</div>
    {!data.entries.length&&<p className="hint">这个月还没有记录，换个月份看看吧。</p>}
    <button type="button" className="primary" disabled={busy||!selected.length} onClick={create}>＋ 创建手动草稿</button><button type="button" className="textbtn" disabled title="选择 AI 服务商并接入后开放">AI 生成 · 待接入</button>
    <h3 className="monthly-subtitle">已保存的版本</h3>{!data.memories.length&&<p className="hint">还没有月度回忆。</p>}
    {data.memories.map(m=><button type="button" className={'monthly-version '+(editor?.id===m.id?'active':'')} disabled={busy} key={m.id} onClick={()=>open(m)}><strong>{m.payload.title}</strong><small>{m.payload.status==='saved'?'已收藏':'草稿'} · {new Date(m.updated*1000).toLocaleString('zh-CN')} {m.source_changed?'· 来源有更新':''}</small></button>)}
   </section><section className="monthly-editor">{!editor?<div className="empty"><h3>把一个月，收藏成一段故事</h3><p>选择素材后创建草稿，或打开已保存的版本。</p></div>:<>
    {editor.source_changed&&<p className="monthly-info">来源记录已修改或删除。文案和统计保留保存时的版本；照片及原帖按当前资料显示。可以另建草稿整理最新内容。</p>}
    {!!editor.new_records&&<p className="hint">本月另有 {editor.new_records} 条记录未包含在这份回忆中。</p>}
    <label>回忆标题<input maxLength={100} disabled={busy} value={editor.title} onChange={e=>change('title',e.target.value)}/></label>
    {cover&&<img className="monthly-cover" src={cover.thumb||cover.url} alt="月度回忆封面"/>}
    <label>封面照片<select disabled={busy} value={editor.cover_id||''} onChange={e=>change('cover_id',e.target.value||null)}><option value="">不使用封面</option>{editor.cover_id&&!cover&&<option value={editor.cover_id}>原封面已删除，请重新选择</option>}{photos.map((p,i)=><option key={p.id} value={p.id}>{p.day} · 照片 {i+1}</option>)}</select></label>
    <p className="hint">此版本：{editor.stats.days} 天 · {editor.stats.posts} 条帖子 · {editor.stats.photos} 张照片 · {editor.stats.comments} 条留言</p>
    <label>这个月的故事<textarea rows={8} maxLength={8000} disabled={busy} placeholder="写下这个月想记住的事。这里暂时由你们填写，之后会接入 AI 草稿。" value={editor.body} onChange={e=>change('body',e.target.value)}/></label>
    <h3>值得重看的瞬间</h3><p className="hint">最多选择 6 条，按勾选顺序展示。</p><div className="monthly-highlight-options">{source.map(e=><label key={e.id}><input type="checkbox" disabled={busy||(!editor.highlights.includes(e.id)&&editor.highlights.length>=6)} checked={editor.highlights.includes(e.id)} onChange={event=>change('highlights',event.target.checked?[...editor.highlights,e.id]:editor.highlights.filter(id=>id!==e.id))}/>{e.day} · {e.body.slice(0,30)||'影像回忆'}</label>)}</div>
    {editor.highlights.map(id=>{const e=source.find(e=>e.id===id);return e?<article className="monthly-highlight" key={id}>{e.media.find(m=>m.thumb)&&<img src={e.media.find(m=>m.thumb).thumb} alt="回忆片段" loading="lazy"/>}<h4>{e.day} · {e.author}</h4><p>{e.body}</p>{e.comments.slice(0,3).map(c=><blockquote key={c.id}>{c.author}：{c.body||'发送了表情'} </blockquote>)}<button type="button" className="textbtn" disabled={busy} onClick={()=>visit(e)}>看看那天 →</button></article>:<p key={id} className="hint">一条原帖已删除或移至其他月份。<button type="button" disabled={busy} onClick={()=>change('highlights',editor.highlights.filter(x=>x!==id))}>移除引用</button></p>})}
    <label>{me.name}留给这个月的一句话<textarea rows={2} maxLength={500} disabled={busy} value={editor.note} onChange={e=>change('note',e.target.value)}/></label>
    {Object.entries(editor.notes).filter(([id])=>id!==me.id).map(([id,n])=><blockquote key={id}>{n.name}：{n.text||'还没有留言'}</blockquote>)}
    <div className="monthly-actions"><button type="button" disabled={busy||!editor.title.trim()} onClick={()=>save('draft')}>保存草稿</button><button type="button" className="primary" disabled={busy||!editor.title.trim()} onClick={()=>save('saved')}>{busy?'正在保存…':'收藏这份回忆'}</button></div>
   </>}</section></div>
  </>}
 </dialog>,document.body);
}
