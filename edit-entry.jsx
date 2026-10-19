import React, {useEffect,useState} from 'react';
import {createPortal} from 'react-dom';
import {api} from './api.mjs';
import TagPicker from './tags.jsx';
import LocationPicker from './locations.jsx';

export function EditEntry({entry,onClose,onSaved}){
 const [location,setLocation]=useState(entry.location||null);
 const [chosenTags,setChosenTags]=useState(entry.tags||[]),[tagBusy,setTagBusy]=useState(false);
 const dialog=React.useRef(null);
 const [day,setDay]=useState(entry.day),[body,setBody]=useState(entry.body),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{const node=dialog.current,previous=document.activeElement,overflow=document.body.style.overflow;node.showModal();document.body.style.overflow='hidden';return()=>{node.close();document.body.style.overflow=overflow;if(previous?.isConnected)previous.focus({preventScroll:true})}},[]);
 function close(){if(busy||tagBusy)return;if((JSON.stringify(location)!==JSON.stringify(entry.location||null)||day!==entry.day||body!==entry.body||JSON.stringify(chosenTags.map(t=>t.id).sort())!==JSON.stringify((entry.tags||[]).map(t=>t.id).sort()))&&!confirm('放弃尚未保存的修改？'))return;onClose()}
 async function submit(event){event.preventDefault();if(busy||tagBusy)return;if(location&&!location.name.trim()){setError('请填写地点名称，或移除地点');return}setBusy(true);setError('');try{await api('/api/entries/'+entry.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({day,body,location,tag_ids:chosenTags.map(t=>t.id),original:{day:entry.day,body:entry.body,location:entry.location||null,tag_ids:(entry.tags||[]).map(t=>t.id)}})})}catch(e){setError(e.message);setBusy(false);return}onSaved(day)}
 return createPortal(<dialog ref={dialog} className="edit-dialog" aria-labelledby="edit-title" onCancel={e=>{e.preventDefault();close()}}>
  <div className="detail-title"><h2 id="edit-title">编辑这一天的回忆</h2><button type="button" disabled={busy||tagBusy} onClick={close} aria-label="关闭编辑">×</button></div>
  <form onSubmit={submit}><label>记录日期<input type="date" required min="1900-01-01" max="2200-12-31" value={day} disabled={busy} onChange={e=>setDay(e.target.value)}/></label><label>今天想记住什么？<textarea autoFocus rows="6" maxLength={5000} value={body} disabled={busy} onChange={e=>setBody(e.target.value)}/></label><p className="hint">{body.length}/5000 字 · 可修改文字、日期、地点和标签，原有照片、视频及留言会保留。</p><LocationPicker value={location} onChange={setLocation} disabled={busy} request={api}/><TagPicker value={chosenTags} onChange={setChosenTags} disabled={busy} onBusyChange={setTagBusy} request={api}/>{error&&<p className="error" role="alert">{error}</p>}<div className="edit-actions"><button type="button" className="textbtn" disabled={busy||tagBusy} onClick={close}>取消</button><button className="primary" disabled={busy||tagBusy||(!body.trim()&&!entry.media.length)}>{busy?'正在保存…':'保存修改'}</button></div></form>
 </dialog>,document.body);
}

