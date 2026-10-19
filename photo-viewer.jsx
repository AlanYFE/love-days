import React, {useEffect,useState} from 'react';
import {createPortal} from 'react-dom';
import {LivePhoto} from './live-photos.jsx';

export function PhotoViewer({photos,initialIndex,onClose}){
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

