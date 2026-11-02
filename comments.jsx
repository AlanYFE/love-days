import React, {useState} from 'react';
import {api} from './api.mjs';
import {EmojiPicker,Reactions} from './emoji-picker.jsx';

export function Comments({entry, me, refresh}) {
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
  <div className="comment-list">{comments.length>2&&<details className="older-comments"><summary>查看更早的 {comments.length-2} 条留言</summary>{comments.slice(0,-2).map(c=><div className="comment" key={c.id} id={'comment-'+c.id} tabIndex={-1}>
   <div className="comment-meta"><strong>{c.author}</strong><time dateTime={new Date(c.created*1000).toISOString()}>{new Date(c.created*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})}</time>{c.user_id===me.id&&<button type="button" className="textbtn" disabled={busy} onClick={()=>remove(c)} aria-label={'删除'+c.author+'的这条评论'}>删除</button>}</div>
   {c.body&&<p className="comment-body">{c.body}</p>}
   {!!c.emojis?.length&&<div className="comment-stickers">{c.emojis.map((emoji,i)=><a key={i} href={emoji.url} target="_blank" rel="noreferrer"><img src={emoji.url} loading="lazy" alt={emoji.name} title={emoji.name}/></a>)}</div>}
   {!c.is_ai && <Reactions kind="comments" target={c} me={me} refresh={refresh}/>}
  </div>)}</details>}{comments.slice(-2).map(c=><div className="comment" key={c.id} id={'comment-'+c.id} tabIndex={-1}>
   <div className="comment-meta"><strong>{c.author}</strong><time dateTime={new Date(c.created*1000).toISOString()}>{new Date(c.created*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})}</time>{c.user_id===me.id&&<button type="button" className="textbtn" disabled={busy} onClick={()=>remove(c)} aria-label={'删除'+c.author+'的这条评论'}>删除</button>}</div>
   {c.body&&<p className="comment-body">{c.body}</p>}
   {!!c.emojis?.length&&<div className="comment-stickers">{c.emojis.map((emoji,i)=><a key={i} href={emoji.url} target="_blank" rel="noreferrer"><img src={emoji.url} loading="lazy" alt={emoji.name} title={emoji.name}/></a>)}</div>}
   {!c.is_ai && <Reactions kind="comments" target={c} me={me} refresh={refresh}/>}
  </div>)}</div>
  <form className="comment-form" onSubmit={submit}>
   <textarea aria-label="评论内容" placeholder="想对你说……" rows="2" maxLength={1000} value={draft} disabled={busy} onChange={e=>setDraft(e.target.value)}/>
   {!!chosen.length&&<div className="chosen-emojis">{chosen.map((emoji,i)=><button key={i} type="button" disabled={busy} onClick={()=>setChosen(items=>items.filter((_,j)=>j!==i))} aria-label={'移除'+emoji.name}><img src={emoji.url} alt={emoji.name}/><span>×</span></button>)}</div>}
   <div className="comment-actions"><EmojiPicker disabled={busy||chosen.length>=8} onSelect={emoji=>setChosen(items=>items.length<8?[...items,emoji]:items)}/><span>{draft.length}/1000 · {chosen.length}/8</span><button className="primary" disabled={busy||(!draft.trim()&&!chosen.length)}>{busy?'处理中…':'发送留言'}</button></div>
  </form>
  {error&&<p role="alert" className="error">{error}</p>}
 </section>;
}

