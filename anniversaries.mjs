// Calendar arithmetic uses UTC date-only values, never elapsed local hours.
const DAY=86400000;
export const ordinal=day=>Date.parse(day+'T00:00:00Z')/DAY;
export const daysBetween=(a,b)=>ordinal(b)-ordinal(a);
export function chinaToday(now=new Date()){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
 const get=type=>parts.find(p=>p.type===type).value;
 return `${get('year')}-${get('month')}-${get('day')}`;
}
export function eventsForYear(config,year){
 if(!config)return [];
 const result=[],start=config.together,sy=Number(start.slice(0,4));
 const add=(day,label,kind)=>result.push({day,label,kind,id:day+':'+label});
 for(const person of config.birthdays){
  const age=year-Number(person.day.slice(0,4));
  if(age>=0)add(`${year}${person.day.slice(4)}`,age?`${person.name} ${age} 岁生日`:`${person.name}出生啦`,'birthday');
 }
 if(year>=sy){
  const years=year-sy;
  add(`${year}${start.slice(4)}`,years?`在一起 ${years} 周年`:'我们在一起啦','love');
  // The configured start date is March 21: half-year anniversaries are September 21.
  const half=new Date(start+'T00:00:00Z');half.setUTCFullYear(year);half.setUTCMonth(half.getUTCMonth()+6);
  const halfDay=half.toISOString().slice(0,10);
  if(Number(halfDay.slice(0,4))===year)add(halfDay,years?`在一起 ${years} 年半`:'在一起半年','love');
  const from=`${year}-01-01`,to=`${year}-12-31`;
  const first=Math.max(100,Math.ceil((daysBetween(start,from)+1)/100)*100);
  for(let n=first;n<=daysBetween(start,to)+1;n+=100){
   const day=new Date((ordinal(start)+n-1)*DAY).toISOString().slice(0,10);
   add(day,`在一起第 ${n} 天`,'milestone');
  }
 }
 return result.sort((a,b)=>a.day.localeCompare(b.day)||a.label.localeCompare(b.label));
}
export function upcomingEvents(config,today,limit=4){
 const year=Number(today.slice(0,4));
 return [...eventsForYear(config,year),...eventsForYear(config,year+1)].filter(e=>e.day>=today).slice(0,limit);
}
