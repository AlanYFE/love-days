import React, {createContext,useContext,useState} from 'react';
import {api} from './api.mjs';
import {EmojiPicker,Reactions} from './emoji-picker.jsx';

const DraftContext=createContext(null);
const emptyDraft={body:'',emojis:[],sending:false,error:''};

export function CommentDrafts({children}){
 const [drafts,setDrafts]=useState(()=>new Map());
 function update(id,patch){
  setDrafts(previous=>{
   const next=new Map(previous);
   const draft={...(previous.get(id)||emptyDraft),...patch};
   if(draft.body||draft.emojis.length||draft.sending||draft.error)next.set(id,draft);
   else next.delete(id);
   return next;
  });
 }
 return <DraftContext.Provider value={{drafts,update}}>{children}</DraftContext.Provider>;
}

export function Comments({entry, me, refresh}) {
 const {drafts,update}=useContext(DraftContext);
 const {body:draft,emojis:chosen,sending,error:sendError}=drafts.get(entry.id)||emptyDraft;
 const [deleting,setDeleting]=useState(false),[error,setError]=useState('');
 const busy=sending||deleting;
 const comments=entry.comments||[];
 async function submit(event){
  event.preventDefault();if(busy||(!draft.trim()&&!chosen.length))return;
  update(entry.id,{sending:true,error:''});setError('');
  try{
   await api('/api/entries/'+entry.id+'/comments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({body:draft,emoji_ids:chosen.map(e=>e.id)})});
   update(entry.id,{body:'',emojis:[]});
   try{await refresh()}catch{update(entry.id,{error:'评论已保存，列表刷新失败，请刷新页面查看。'})}
  }catch(e){update(entry.id,{error:e.message})}finally{update(entry.id,{sending:false})}
 }
 async function remove(comment){
  if(busy||!confirm('确定删除自己的这条评论？'))return;
  setDeleting(true);setError('');
  try{await api('/api/comments/'+comment.id,{method:'DELETE'});await refresh()}
  catch(e){setError(e.message)}finally{setDeleting(false)}
 }
 return <section className="comments" aria-label="帖子评论">
  <h3>留言 <span>{comments.length}</span></h3>
  {!comments.length&&<p className="comment-empty">给这个小日子留句话吧。</p>}
  <div className="comment-list">{comments.length>2&&<details className="older-comments"><summary>查看更早的 {comments.length-2} 条留言</summary>{comments.slice(0,-2).map(c=><div className="comment" key={c.id} id={'comment-'+c.id} tabIndex={-1}>
   <div className="comment-meta"><strong>{c.author}</strong><time dateTime={new Date(c.created*1000).toISOString()}>{new Date(c.created*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})}</time>{c.user_id===me.id&&<button type="button" className="textbtn" disabled={busy} onClick={()=>remove(c)} aria-label={'删除'+c.author+'的这条评论'}>删除</button>}</div>
   {c.body&&<p className="comment-body">{c.body}</p>}
   {!!c.emojis?.length&&<div className="comment-stickers">{c.emojis.map((emoji,i)=><a key={i} href={emoji.url} target="_blank" rel="noreferrer"><img src={emoji.url} loading="lazy" alt={emoji.name} title={emoji.name}/></a>)}</div>}
   <Reactions kind="comments" target={c} me={me} refresh={refresh}/>
  </div>)}</details>}{comments.slice(-2).map(c=><div className="comment" key={c.id} id={'comment-'+c.id} tabIndex={-1}>
   <div className="comment-meta"><strong>{c.author}</strong><time dateTime={new Date(c.created*1000).toISOString()}>{new Date(c.created*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})}</time>{c.user_id===me.id&&<button type="button" className="textbtn" disabled={busy} onClick={()=>remove(c)} aria-label={'删除'+c.author+'的这条评论'}>删除</button>}</div>
   {c.body&&<p className="comment-body">{c.body}</p>}
   {!!c.emojis?.length&&<div className="comment-stickers">{c.emojis.map((emoji,i)=><a key={i} href={emoji.url} target="_blank" rel="noreferrer"><img src={emoji.url} loading="lazy" alt={emoji.name} title={emoji.name}/></a>)}</div>}
   <Reactions kind="comments" target={c} me={me} refresh={refresh}/>
  </div>)}</div>
  <form className="comment-form" onSubmit={submit}>
   <textarea aria-label="评论内容" placeholder="想对你说……" rows="2" maxLength={1000} value={draft} disabled={busy} onChange={e=>update(entry.id,{body:e.target.value})}/>
   {!!chosen.length&&<div className="chosen-emojis">{chosen.map((emoji,i)=><button key={i} type="button" disabled={busy} onClick={()=>update(entry.id,{emojis:chosen.filter((_,j)=>j!==i)})} aria-label={'移除'+emoji.name}><img src={emoji.url} alt={emoji.name}/><span>×</span></button>)}</div>}
   <div className="comment-actions"><EmojiPicker disabled={busy||chosen.length>=8} onSelect={emoji=>update(entry.id,{emojis:[...chosen,emoji].slice(0,8)})}/><span>{draft.length}/1000 · {chosen.length}/8</span><button className="primary" disabled={busy||(!draft.trim()&&!chosen.length)}>{busy?'处理中…':'发送留言'}</button></div>
  </form>
  {(error||sendError)&&<p role="alert" className="error">{error||sendError}</p>}
 </section>;
}

