import React,{useEffect,useRef,useState} from 'react';
import {isPhoto,isLivePackage,matchingVideo} from './live-upload.mjs';
export function LiveUploads({files,value,onChange,onBusyChange,disabled}){
 useEffect(()=>{let active=true;onBusyChange(true);Promise.all(files.map(async file=>{
  if(isLivePackage(file))return {enabled:true,detected:true,package:true,pair:null,photo:true};
  const pair=matchingVideo(file,files);
  if(!isPhoto(file))return {enabled:false,detected:false,pair:null,photo:false};
  try{const text=new TextDecoder().decode(await file.slice(0,1024*1024).arrayBuffer());const detected=/\b(?:\w+:)?MotionPhoto\s*=\s*["']1["']/.test(text);return {enabled:detected||!!pair,detected,pair,photo:true}}
  catch{return {enabled:!!pair,detected:false,pair,photo:true,failed:true}}
 })).then(items=>{if(active)onChange(items)}).finally(()=>{if(active)onBusyChange(false)});return()=>{active=false}},[files]);
 function update(i,patch){onChange(value.map((v,j)=>i===j?{...v,...patch}:v))}
 return <div className="live-uploads">{files.map((file,i)=>{const item=value[i];return <div className="live-upload" key={i}><div className="live-upload-name"><strong>{file.name}</strong><span>{(file.size/1024/1024).toFixed(1)} MB</span></div>{!item?<p className="hint">正在检测实况…</p>:item.photo?<><p className="hint">{item.package?'实况包将在保存时解包并验证照片和视频。':item.detected?'检测到实况标记，保存时会验证动态视频。':item.pair?`配套视频：${item.pair.name}（请确认是同一张实况）`:item.failed?'文件检测失败，可以重新选图或补选视频。':'未检测到内嵌动态；iPhone 实况可能还需要配套视频。'}</p>{(item.detected||item.pair)&&<label className="live-check"><input type="checkbox" checked={item.enabled} disabled={disabled} onChange={e=>update(i,{enabled:e.target.checked})}/>保留实况<span>取消则只保存静态照片</span></label>}{!item.detected&&<div className="live-pair"><label className="live-pair-button">{item.pair?'更换配套视频':'＋ 补选配套 MOV / MP4'}<input type="file" accept="video/*,.mov,.mp4" disabled={disabled} onChange={e=>{const pair=e.target.files?.[0];if(pair)update(i,{pair,enabled:true});e.target.value=''}}/></label>{item.pair&&<><span>{item.pair.name}</span><button type="button" className="textbtn" disabled={disabled} onClick={()=>update(i,{pair:null,enabled:false})}>移除视频</button></>}</div>}</>:<p className="hint">{value.some(o=>o?.pair===file)?'已配对到照片，不会重复发布为视频；取消保留实况时不上传此视频。':'普通视频'}</p>}</div>})}<p className="hint">实况动态最长 15 秒；配套视频计入 200 MB 总量。从“文件”可导入 .livp，或同时选择同名照片和 MOV/MP4。仅有 HEIC/JPG 不包含动态时，需要补选视频。</p></div>;
}

export function LivePhoto({photo,onLoad,onError,onBackground}){
 const video=useRef(null),timer=useRef(null),held=useRef(false);
 const [playing,setPlaying]=useState(false),[muted,setMuted]=useState(true),[error,setError]=useState('');
 function stop(){clearTimeout(timer.current);if(video.current){video.current.pause();video.current.currentTime=0}setPlaying(false)}
 function play(){if(!video.current)return;setError('');video.current.currentTime=0;setPlaying(true);video.current.play().catch(()=>{setPlaying(false);setError('播放失败，请再点一次 LIVE 或刷新后重试')})}
 useEffect(()=>()=>{clearTimeout(timer.current)},[]);
 function release(){clearTimeout(timer.current);if(held.current){held.current=false;stop()}}
 return <div className="live-photo" onClick={e=>{if(e.target===e.currentTarget)onBackground?.()}} onContextMenu={e=>e.preventDefault()} onPointerDown={e=>{if(e.target.tagName==='BUTTON')return;held.current=false;timer.current=setTimeout(()=>{held.current=true;play()},300)}} onPointerUp={release} onPointerCancel={release} onPointerLeave={release}>
  <img src={photo.url} alt="实况照片封面，长按播放" draggable="false" onLoad={onLoad} onError={onError}/>
  <video ref={video} src={photo.motion_url} muted={muted} playsInline preload="none" className={playing?'playing':''} onEnded={stop} onError={()=>{setPlaying(false);setError('动态视频暂时无法播放，请刷新后重试')}}/>
  <div className="live-controls"><button type="button" aria-pressed={playing} onClick={()=>playing?stop():play()}>{playing?'■ 停止':'◎ LIVE'}</button><button type="button" aria-label={muted?'开启实况声音':'静音实况'} aria-pressed={!muted} onClick={()=>setMuted(v=>!v)}>{muted?'声音关':'声音开'}</button></div>
  {error&&<p className="live-play-error" role="alert">{error}</p>}
 </div>;
}
