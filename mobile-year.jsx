import React from 'react';

export function MobileYear({year, byDay, onChoose}) {
  return <div className="year-months" aria-label={year+' 年，选择月份'}>
    {Array.from({length:12}, (_,month) => {
      const start = new Date(year,month,1);
      const count = new Date(year,month+1,0).getDate();
      const prefix = year+'-'+String(month+1).padStart(2,'0')+'-';
      const offset = (start.getDay()+6)%7;
      return <button type="button" key={month} onClick={()=>onChoose(start)}
        aria-label={'查看'+year+'年'+(month+1)+'月照片月历'}>
        <span>{month+1} 月</span>
        <span className="month-pixels" aria-hidden="true">
          {Array.from({length:count}, (_,i)=>{
            const n = byDay[prefix+String(i+1).padStart(2,'0')]?.count || 0;
            return <i key={i} className={'l'+Math.min(3,n)}
              style={i===0 ? {gridColumnStart:offset+1} : undefined}/>;
          })}
        </span>
      </button>;
    })}
  </div>;
}
