import React, {useEffect,useId,useState} from 'react';

export default function TagPicker({value,onChange,disabled=false,onBusyChange,request}){
 const [tags,setTags]=useState([]),[query,setQuery]=useState(''),[loading,setLoading]=useState(true),[error,setError]=useState(''),[creating,setCreating]=useState(false);
 const inputId=useId();
 useEffect(()=>{let active=true;request('/api/tags').then(items=>{if(active)setTags(items)}).catch(e=>{if(active)setError(e.message)}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[]);
 async function reload(){setLoading(true);setError('');try{setTags(await request('/api/tags'))}catch(e){setError(e.message)}finally{setLoading(false)}}
 const selected=new Set(value.map(t=>t.id));
 const normalized=query.normalize('NFKC').trim().replace(/\s+/g,' ');
 const matches=tags.filter(t=>t.name.toLocaleLowerCase().includes(normalized.toLocaleLowerCase()));
 const exact=tags.find(t=>t.name.toLocaleLowerCase()===normalized.toLocaleLowerCase());
 function toggle(tag){if(disabled||creating)return;onChange(selected.has(tag.id)?value.filter(t=>t.id!==tag.id):value.length<8?[...value,tag]:value)}
 async function create(){
  if(disabled||creating||!normalized||value.length>=8)return;
  setCreating(true);onBusyChange(true);setError('');
  try{const tag=await request('/api/tags',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:normalized})});setTags(items=>items.some(t=>t.id===tag.id)?items:[...items,tag]);if(!selected.has(tag.id))onChange([...value,tag]);setQuery('')}
  catch(e){setError(e.message)}finally{setCreating(false);onBusyChange(false)}
 }
 return <fieldset className="tag-picker" disabled={disabled||creating}>
  <legend>标签 <span>可选 · {value.length}/8</span></legend>
  {!!value.length&&<div className="tag-selected" aria-label="已选标签">{value.map(tag=><button className="tag-chip selected" type="button" key={tag.id} onClick={()=>toggle(tag)} aria-label={'移除标签 '+tag.name}># {tag.name}<span aria-hidden="true"> ×</span></button>)}</div>}
  <label className="tag-search-label" htmlFor={inputId}>搜索或新建标签</label>
  <div className="tag-search"><input id={inputId} value={query} maxLength={24} placeholder="例如：散步、探店、一起打游戏" onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();if(exact){if(!selected.has(exact.id))toggle(exact)}else create()}}}/><button type="button" className="tag-create" disabled={!normalized||value.length>=8||!!exact} onClick={create}>{creating?'创建中…':'＋ 新建'}</button></div>
  {loading?<p className="hint" role="status">正在加载标签…</p>:<div className="tag-options" aria-label="共享标签库">{matches.map(tag=><button className={'tag-chip '+(selected.has(tag.id)?'selected':'')} type="button" key={tag.id} aria-pressed={selected.has(tag.id)} disabled={!selected.has(tag.id)&&value.length>=8} onClick={()=>toggle(tag)}># {tag.name}{selected.has(tag.id)&&' ✓'}</button>)}{!matches.length&&<p className="hint">{normalized?'没有匹配的标签，可以点击“新建”。':'还没有标签，创建你们的第一个标签吧。'}</p>}</div>}
  <p className="hint">两人共用 · 新建标签会加入标签库，取消发帖也会保留。{value.length>=8&&' 已选满 8 个，可先移除再选择。'}</p>
  {error&&<div className="tag-error"><p className="error" role="alert">{error}</p><button type="button" className="textbtn" onClick={reload} disabled={loading}>重新加载标签</button></div>}
 </fieldset>;
}
