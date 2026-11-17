import React, {createContext,useContext,useState,useEffect,useRef} from 'react';
import {LiveUploads} from './live-photos.jsx';
import {uploadItems,isPhoto,isLivePackage} from './live-upload.mjs';
import {PhotoViewer} from './photo-viewer.jsx';
import {api} from './api.mjs';
import {EmojiPicker,Reactions} from './emoji-picker.jsx';

const DraftContext=createContext(null);
const emptyDraft={body:'',emojis:[],files:[],liveOptions:[],sending:false,error:''};

export function CommentDrafts({children}){
 const [drafts,setDrafts]=useState(()=>new Map());
 function update(id,patch){
  setDrafts(previous=>{
   const next=new Map(previous);
   const draft={...(previous.get(id)||emptyDraft),...patch};
   if(draft.body||draft.emojis.length||draft.files.length||draft.sending||draft.error)next.set(id,draft);
   else next.delete(id);
   return next;
  });
 }
 return <DraftContext.Provider value={{drafts,update}}>{children}</DraftContext.Provider>;
}

export function Comments({entry, me, refresh}) {
 const {drafts,update}=useContext(DraftContext);
 const {body:draft,emojis:chosen,files,liveOptions,sending,error:sendError}=drafts.get(entry.id)||emptyDraft;
 const [deleting,setDeleting]=useState(false),[error,setError]=useState('');
 const [writing,setWriting]=useState(Boolean(draft||chosen.length||files.length));
 const [gallery,setGallery]=useState(null);
 const imageInput=useRef(null);
 const [liveDetecting,setLiveDetecting]=useState(false);
 const busy=sending||deleting||liveDetecting;
 function removeImage(index){
  const removed=files[index],pair=liveOptions[index]?.pair;
  update(entry.id,{files:files.filter(f=>f!==removed&&f!==pair),liveOptions:liveOptions.filter(o=>o.file!==removed&&o.file!==pair).map(o=>o.pair===removed?{...o,pair:null,enabled:false}:o)});
 }
 function chooseImages(event){
  const added=Array.from(event.target.files||[]);event.target.value='';
  if(!added.length)return;
  if(files.length+added.length>8){update(entry.id,{error:'每条留言最多 4 张图片或实况，可同时选 4 组照片与视频'});return}
  if(added.some(f=>f.size>10*1024*1024)){update(entry.id,{error:'每张图片不能超过 10 MB'});return}
  update(entry.id,{files:[...files,...added],error:''});
 }
 const comments=entry.comments||[];
 async function submit(event){
  event.preventDefault();if(busy||(!draft.trim()&&!chosen.length&&!files.length))return;
  update(entry.id,{sending:true,error:''});setError('');
  try{
   const items=uploadItems(files,liveOptions);
   if(items.length>4)throw Error('每条留言最多 4 张图片或实况');
   if(items.some(({file})=>!isPhoto(file)&&!isLivePackage(file)))throw Error('评论仅支持图片或实况；请为视频选择同名照片或补选到对应照片下');
   if(items.some(({file,option:o})=>file.size+(o.enabled&&o.pair?o.pair.size:0)>10*1024*1024))throw Error('每张实况的照片与视频合计不能超过 10 MB');
   const form=new FormData();form.set('body',draft);form.set('emoji_ids',JSON.stringify(chosen.map(e=>e.id)));
   form.set('live_options',JSON.stringify(items.map(({option:o})=>({enabled:!!o.enabled,paired:!!(o.enabled&&o.pair)}))));
   items.forEach(({file,option:o},i)=>{form.append('images',file);if(o.enabled&&o.pair)form.append('live_'+i,o.pair)});
   await api('/api/entries/'+entry.id+'/comments',{method:'POST',body:form});
   update(entry.id,{body:'',emojis:[],files:[],liveOptions:[]});setWriting(false);
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
   {!!c.images?.length&&<div className="comment-images">{c.images.map((image,i)=><button type="button" key={image.id} onClick={()=>setGallery({photos:c.images,index:i})} aria-label={`查看留言图片 ${i+1}`}><img src={image.thumb} alt={`留言图片 ${i+1}`} loading="lazy"/>{image.live&&<span className="comment-live-badge">◎ LIVE</span>}</button>)}</div>}
   <Reactions kind="comments" target={c} me={me} refresh={refresh}/>
  </div>)}</details>}{comments.slice(-2).map(c=><div className="comment" key={c.id} id={'comment-'+c.id} tabIndex={-1}>
   <div className="comment-meta"><strong>{c.author}</strong><time dateTime={new Date(c.created*1000).toISOString()}>{new Date(c.created*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})}</time>{c.user_id===me.id&&<button type="button" className="textbtn" disabled={busy} onClick={()=>remove(c)} aria-label={'删除'+c.author+'的这条评论'}>删除</button>}</div>
   {c.body&&<p className="comment-body">{c.body}</p>}
   {!!c.emojis?.length&&<div className="comment-stickers">{c.emojis.map((emoji,i)=><a key={i} href={emoji.url} target="_blank" rel="noreferrer"><img src={emoji.url} loading="lazy" alt={emoji.name} title={emoji.name}/></a>)}</div>}
   {!!c.images?.length&&<div className="comment-images">{c.images.map((image,i)=><button type="button" key={image.id} onClick={()=>setGallery({photos:c.images,index:i})} aria-label={`查看留言图片 ${i+1}`}><img src={image.thumb} alt={`留言图片 ${i+1}`} loading="lazy"/>{image.live&&<span className="comment-live-badge">◎ LIVE</span>}</button>)}</div>}
   <Reactions kind="comments" target={c} me={me} refresh={refresh}/>
  </div>)}</div>
  {!writing?<button type="button" className="emoji-trigger write-comment" onClick={()=>setWriting(true)}>留句话</button>:<form className="comment-form" onSubmit={submit}>
   <textarea autoFocus aria-label="评论内容" placeholder="想对你说……" rows="2" maxLength={1000} value={draft} disabled={busy} onChange={e=>update(entry.id,{body:e.target.value})}/>
   {!!chosen.length&&<div className="chosen-emojis">{chosen.map((emoji,i)=><button key={i} type="button" disabled={busy} onClick={()=>update(entry.id,{emojis:chosen.filter((_,j)=>j!==i)})} aria-label={'移除'+emoji.name}><img src={emoji.url} alt={emoji.name}/><span>×</span></button>)}</div>}
   {!!files.length&&<div className="comment-image-drafts">{files.map((file,i)=><DraftImage key={i} file={file} disabled={busy} onRemove={()=>removeImage(i)}/>)}</div>}
   <p className="hint">最多 4 张图片或实况；每张含配套视频合计 10 MB，动态最长 15 秒。</p>
   <input ref={imageInput} type="file" hidden multiple accept="image/*,video/*" disabled={busy||files.length>=8} aria-label="选择留言图片" onChange={chooseImages}/>
   {!!files.length&&<LiveUploads files={files} value={liveOptions} onChange={options=>update(entry.id,{liveOptions:options})} onBusyChange={setLiveDetecting} disabled={busy} limitHint="每张实况含配套视频合计 10 MB，动态最长 15 秒。"/>}
   <label className="comment-file-import file-picker">从文件导入实况<input className="file-picker-input" type="file" multiple disabled={busy||files.length>=8} onChange={chooseImages} aria-label="导入留言实况文件"/></label>
   <div className="comment-actions"><button type="button" className="emoji-trigger" disabled={busy||files.length>=8} onClick={()=>imageInput.current?.click()}>＋ 图片{files.length?` ${uploadItems(files,liveOptions).length}/4`:""}</button><EmojiPicker disabled={busy||chosen.length>=8} onSelect={emoji=>update(entry.id,{emojis:[...chosen,emoji].slice(0,8)})}/><span>{draft.length}/1000 · {chosen.length}/8</span><button className="primary" disabled={busy||(!draft.trim()&&!chosen.length&&!files.length)}>{busy?'处理中…':'发送留言'}</button></div>
  </form>}
  {gallery&&<PhotoViewer photos={gallery.photos} initialIndex={gallery.index} onClose={()=>setGallery(null)}/>}
  {(error||sendError)&&<p role="alert" className="error">{error||sendError}</p>}
 </section>;
}


function DraftImage({file,disabled,onRemove}){
 const [url,setUrl]=useState(''),[failed,setFailed]=useState(false);
 useEffect(()=>{const value=URL.createObjectURL(file);setUrl(value);setFailed(false);return()=>URL.revokeObjectURL(value)},[file]);
 return <div className="comment-image-draft">{url&&!failed?<img src={url} alt={file.name} onError={()=>setFailed(true)}/>:<span className="hint">保存后可查看</span>}<span className="draft-image-name" title={file.name}>{file.name}</span><button type="button" disabled={disabled} onClick={onRemove} aria-label={'移除图片 '+file.name}>×</button></div>;
}
