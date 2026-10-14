import React,{useState,useEffect,useRef} from 'react';
import {createPortal} from 'react-dom';
export function LocationDisplay({value}){
 if(!value)return null;
 const label=[value.city,value.name].filter(Boolean).join(' · ');
 if(value.lat==null)return <p className="entry-location">📍 {label}</p>;
 const clean=text=>(text||'').replaceAll(';','；').replaceAll('|','｜').replaceAll(':','：');
 const params=new URLSearchParams({marker:`coord:${value.lat},${value.lng};title:${clean(value.name)};addr:${clean(value.address||value.city)}`,referer:'LoveDays'});
 return <a className="entry-location" href={'https://apis.map.qq.com/uri/v1/marker?'+params} target="_blank" rel="noopener noreferrer" title="在腾讯地图查看">📍 {label} ↗</a>;
}
function MapPicker({config,value,onSelect,onClose}){
 const dialog=useRef(null),frame=useRef(null),timerRef=useRef(null);
 const [waiting,setWaiting]=useState(true),[error,setError]=useState('');
 useEffect(()=>{const node=dialog.current,previous=document.activeElement,overflow=document.body.style.overflow;node.showModal();document.body.style.overflow='hidden';const timer=timerRef.current=setTimeout(()=>setError('地图加载较慢或服务不可用，可以关闭后手动填写地点。'),12000);return()=>{clearTimeout(timer);node.close();document.body.style.overflow=overflow;previous?.isConnected&&previous.focus({preventScroll:true})}},[]);
 useEffect(()=>{function receive(event){
  if(!['https://apis.map.qq.com','https://mapapi.qq.com'].includes(event.origin)||event.source!==frame.current?.contentWindow)return;
  const d=event.data;if(!d||d.module!=='locationPicker')return;
  const lat=d.latlng?.lat,lng=d.latlng?.lng;
  if(typeof lat!=='number'||typeof lng!=='number'||!Number.isFinite(lat)||!Number.isFinite(lng)||Math.abs(lat)>90||Math.abs(lng)>180||typeof d.poiname!=='string'||!d.poiname.trim()){setError('地图返回的地点不完整，请重新选择。');return}
  onSelect({name:d.poiname.trim().slice(0,120),city:typeof d.cityname==='string'?d.cityname.slice(0,80):'',address:typeof d.poiaddress==='string'?d.poiaddress.slice(0,300):'',lat,lng,source:'tencent',coordinate_system:'gcj02'});
 }window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive)},[onSelect]);
 const params=new URLSearchParams({search:'1',type:'1',key:config.key,referer:config.referer,coordtype:'5'});
 if(value?.lat!=null)params.set('coord',`${value.lat},${value.lng}`);
 return createPortal(<dialog ref={dialog} className="location-dialog" aria-label="选择帖子地点" onCancel={e=>{e.preventDefault();e.stopPropagation();onClose()}}><div className="detail-title"><h2>选择地点</h2><button type="button" onClick={onClose} aria-label="关闭地图">×</button></div><p className="hint">搜索地点或拖动地图后确认。定位不可用时仍可搜索；关闭地图会保留帖子草稿。</p>{waiting&&<p role="status" className="hint">正在打开腾讯地图…</p>}{error&&<p className="hint" role="status">{error}</p>}<iframe ref={frame} title="腾讯地图选点" src={'https://apis.map.qq.com/tools/locpicker?'+params} referrerPolicy="strict-origin-when-cross-origin" allow="geolocation https://apis.map.qq.com https://mapapi.qq.com" onLoad={()=>{setWaiting(false);clearTimeout(timerRef.current)}}/><button type="button" className="textbtn" onClick={onClose}>关闭，改为手动填写</button></dialog>,document.body);
}
export default function LocationPicker({value,onChange,disabled,request}){
 const [config,setConfig]=useState(null),[open,setOpen]=useState(false),[error,setError]=useState('');
 useEffect(()=>{let active=true;request('/api/map-config').then(c=>{if(active)setConfig(c)}).catch(()=>{if(active)setError('地图暂时不可用，仍可手动填写。')});return()=>{active=false}},[request]);
 function manual(field,text){const next={name:value?.name||'',city:value?.city||'',address:'',lat:null,lng:null,source:'manual',coordinate_system:null,[field]:text};onChange(next.name||next.city?next:null)}
 return <fieldset className="location-picker" disabled={disabled}><legend>📍 地点（选填）</legend><div className="location-fields"><label>地点名称<input maxLength={120} value={value?.name||''} onChange={e=>manual('name',e.target.value)} placeholder="例如：平江路 / 第一次约会的地方"/></label><label>城市<input maxLength={80} value={value?.city||''} onChange={e=>manual('city',e.target.value)} placeholder="例如：苏州"/></label></div>{value?.lat!=null&&<p className="hint">已保存地图坐标 · {value.address}。手动修改名称或城市会清除坐标，可重新选点。</p>}<div className="location-actions"><button type="button" className="emoji-trigger" disabled={disabled||!config?.key} onClick={()=>setOpen(true)}>地图搜索 / 选点</button>{value&&<button type="button" className="textbtn" onClick={()=>onChange(null)}>移除地点</button>}</div>{!config?.key&&<p className="hint">{error||'可先手动填写地点；地图配置完成后可搜索选点。'}</p>}{open&&<MapPicker config={config} value={value} onClose={()=>setOpen(false)} onSelect={v=>{onChange(v);setOpen(false)}}/>}</fieldset>;
}
