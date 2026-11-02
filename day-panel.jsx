import React,{useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';

export function useMobileLayout(){
 const [mobile,setMobile]=useState(()=>window.matchMedia('(max-width: 760px)').matches);
 useEffect(()=>{const query=window.matchMedia('(max-width: 760px)');const change=()=>setMobile(query.matches);query.addEventListener('change',change);return()=>query.removeEventListener('change',change)},[]);
 return mobile;
}

// One detail tree: an inline sidebar on desktop, a native modal sheet on mobile.
export function DayPanel({day,open,onClose,children,mobile}){
 const dialog=useRef(null);
 useEffect(()=>{
  if(!mobile||!open)return;
  const node=dialog.current,previous=document.activeElement,overflow=document.body.style.overflow;
  node.showModal();document.body.style.overflow='hidden';
  return()=>{node.close();document.body.style.overflow=overflow;if(previous?.isConnected)previous.focus({preventScroll:true})};
 },[mobile,open]);
 useEffect(()=>{if(mobile&&open&&dialog.current)dialog.current.scrollTop=0},[day,mobile,open]);
 if(!mobile)return <aside className="panel detail" id="day-detail">{children}</aside>;
 return createPortal(<dialog ref={dialog} id="day-detail" className="panel detail day-sheet" aria-labelledby="day-title" onCancel={e=>{e.preventDefault();onClose()}} onClick={e=>{if(e.target===dialog.current){const r=dialog.current.getBoundingClientRect();if(e.clientY<r.top||e.clientX<r.left||e.clientX>r.right)onClose()}}}><div className="sheet-handle" aria-hidden="true"/>{children}</dialog>,document.body);
}
