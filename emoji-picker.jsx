import React, {useEffect,useState} from 'react';
import {createPortal} from 'react-dom';
import {api} from './api.mjs';

export const EmojiContext=React.createContext({emojis:[],reloadEmojis:async()=>{}});
export function EmojiPicker({onSelect,label='☺ 表情',disabled=false}){
 const {emojis,reloadEmojis}=React.useContext(EmojiContext);
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[name,setName]=useState('');
 const trigger=React.useRef(null);
 function close(){if(busy)return;setOpen(false);trigger.current?.focus()}
 useEffect(()=>{if(!open)return;const key=e=>{if(e.key==='Escape'&&!busy){e.preventDefault();e.stopPropagation();setOpen(false);trigger.current?.focus()}};document.addEventListener('keydown',key);return()=>document.removeEventListener('keydown',key)},[open,busy]);
 async function upload(event){
  const file=event.target.files?.[0];event.target.value='';if(!file)return;
  if(file.size>5*1024*1024){setError('表情图片不能超过 5 MB');return}
  const data=new FormData();data.append('file',file);data.append('name',name.trim()||file.name.replace(/\.[^.]+$/,'').slice(0,24)||'小表情');
  setBusy(true);setError('');
  try{await api('/api/emojis',{method:'POST',body:data});setName('');try{await reloadEmojis()}catch{setError('表情已上传，请关闭并重新打开表情库查看。')}}catch(e){setError(e.message)}finally{setBusy(false)}
 }
 return <><button type="button" ref={trigger} className="emoji-trigger" disabled={disabled} aria-haspopup="dialog" aria-expanded={open} onClick={()=>{setOpen(true);setError('');reloadEmojis().catch(e=>setError(e.message))}}>{label}</button>{open&&createPortal(<div className="emoji-overlay" onClick={e=>{if(e.target===e.currentTarget)close()}}><section className="emoji-picker" role="dialog" aria-modal="true" aria-label="我们的表情库"><div className="detail-title"><div><h2>我们的表情库</h2><p>你上传的表情，对方也能使用。</p></div><button type="button" autoFocus disabled={busy} onClick={close} aria-label="关闭表情库">×</button></div><div className="emoji-grid">{emojis.map(emoji=>onSelect?<button type="button" key={emoji.id} title={emoji.name} disabled={busy} onClick={()=>{onSelect(emoji);close()}}><img loading="lazy" src={emoji.url} alt={emoji.name}/><span>{emoji.name}</span></button>:<a key={emoji.id} href={emoji.url} target="_blank" rel="noreferrer" title={emoji.name}><img loading="lazy" src={emoji.url} alt={emoji.name}/><span>{emoji.name}</span></a>)}</div>{!emojis.length&&<p className="emoji-empty">还没有表情，上传第一张喜欢的图片吧。</p>}<div className="emoji-upload"><label>表情名称（可选）<input value={name} maxLength={24} disabled={busy} onChange={e=>setName(e.target.value)} placeholder="例如：抱抱、好耶"/></label><label className="emoji-upload-button">{busy?'正在上传…':'＋ 上传图片 / GIF'}<input type="file" disabled={busy} accept="image/jpeg,image/png,image/webp,image/gif" onChange={upload}/></label><p className="hint">单个 ≤ 5 MB · 最长边 2048 像素 · 动画 ≤ 200 帧<br/>共享库 {emojis.length}/100；GIF 保留动画。</p></div>{error&&<p className="error" role="alert">{error}</p>}</section></div>,trigger.current?.closest('dialog')||document.body)}</>;
}
export function Reactions({kind,target,me,refresh}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const reactions=target.reactions||[];
 async function choose(emoji){
  if(busy)return;const existing=reactions.find(r=>r.emoji.id===emoji.id);const active=!existing?.user_ids.includes(me.id);
  setBusy(true);setError('');
  try{await api(`/api/${kind}/${target.id}/reactions/${emoji.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({active})});try{await refresh()}catch{setError('回应已保存，请刷新页面查看。')}}catch(e){setError(e.message)}finally{setBusy(false)}
 }
 return <div className="reaction-section"><div className="reaction-row">{reactions.map(r=><button type="button" className={'reaction-chip '+(r.user_ids.includes(me.id)?'mine':'')} key={r.emoji.id} aria-pressed={r.user_ids.includes(me.id)} aria-label={`${r.emoji.name}，${r.count} 人回应${r.user_ids.includes(me.id)?'，点击取消':'，点击加入'}`} title={r.emoji.name} disabled={busy} onClick={()=>choose(r.emoji)}><img src={r.emoji.url} alt="" loading="lazy"/><span>{r.count}</span></button>)}<EmojiPicker onSelect={choose} disabled={busy} label="☺ ＋"/></div>{error&&<p role="alert" className="error">{error}</p>}</div>;
}

