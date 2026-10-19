import React, {useState} from 'react';
import {chinaToday} from './anniversaries.mjs';

export function MonthSelector({month,view,onChange}){
 const dialog=React.useRef(null);
 const [year,setYear]=useState(month.getFullYear()),[selectedMonth,setSelectedMonth]=useState(month.getMonth());
 function open(){setYear(month.getFullYear());setSelectedMonth(month.getMonth());dialog.current.showModal()}
 function jump(event){event.preventDefault();onChange(new Date(year,selectedMonth,1));dialog.current.close()}
 function current(){onChange(new Date(chinaToday().slice(0,7)+'-01T12:00:00'));dialog.current.close()}
 return <><button type="button" className="month-title" aria-haspopup="dialog" aria-label="选择年份和月份" title="点击选择年份和月份" onClick={open}>{month.getFullYear()} 年{view==='month'?` ${month.getMonth()+1} 月`:''}<span aria-hidden="true">⌄</span></button>
 <dialog ref={dialog} className="month-dialog" aria-labelledby="month-dialog-title" onClick={e=>{if(e.target===dialog.current){const r=dialog.current.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.current.close()}}}>
  <div className="detail-title"><h2 id="month-dialog-title">跳到某个日子</h2><button type="button" className="month-close" aria-label="关闭年月选择" onClick={()=>dialog.current.close()}>×</button></div>
  <p>选好年份和月份，去看看那时的我们。</p>
  <form onSubmit={jump}><div className="month-fields"><label>年份<select value={year} onChange={e=>setYear(Number(e.target.value))}>{Array.from({length:301},(_,i)=>1900+i).map(y=><option key={y} value={y}>{y} 年</option>)}</select></label><label>月份<select value={selectedMonth} onChange={e=>setSelectedMonth(Number(e.target.value))}>{Array.from({length:12},(_,i)=><option key={i} value={i}>{i+1} 月</option>)}</select></label></div>
  <div className="month-dialog-actions"><button type="button" className="textbtn" onClick={current}>回到本月</button><button type="submit" className="primary">跳转</button></div></form>
 </dialog></>;
}

