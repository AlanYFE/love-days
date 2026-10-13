import test from 'node:test';
import assert from 'node:assert/strict';
import {eventsForYear,daysBetween,chinaToday,upcomingEvents} from '../anniversaries.mjs';
const config={together:'2026-03-21',birthdays:[{name:'飞飞',day:'2000-09-22'},{name:'巧巧',day:'2000-08-25'}]};
test('inclusive milestones and calendar anniversaries',()=>{
 const events=eventsForYear(config,2026),day=label=>events.find(e=>e.label===label)?.day;
 assert.equal(day('在一起第 100 天'),'2026-06-28');
 assert.equal(day('在一起第 200 天'),'2026-10-06');
 assert.equal(day('在一起半年'),'2026-09-21');
 assert.equal(day('飞飞 26 岁生日'),'2026-09-22');
 assert.equal(day('巧巧 26 岁生日'),'2026-08-25');
 assert.equal(eventsForYear(config,2027).find(e=>e.label==='在一起 1 周年').day,'2027-03-21');
 assert.equal(eventsForYear(config,2027).find(e=>e.label==='在一起 1 年半').day,'2027-09-21');
 assert.equal(eventsForYear(config,2025).filter(e=>e.kind!=='birthday').length,0);
});
test('cross-year upcoming, today, leap year and China midnight',()=>{
 assert.equal(upcomingEvents(config,'2026-12-31')[0].day,'2027-01-14');
 assert.equal(upcomingEvents(config,'2026-09-21')[0].label,'在一起半年');
 assert.equal(daysBetween('2028-02-28','2028-03-01'),2);
 assert.equal(chinaToday(new Date('2026-10-13T15:59:59Z')),'2026-10-13');
 assert.equal(chinaToday(new Date('2026-10-13T16:00:00Z')),'2026-10-14');
 for(let year=2026;year<=2200;year++)for(const event of eventsForYear(config,year)){
  assert.equal(Number(event.day.slice(0,4)),year);
  if(event.kind==='milestone')assert.equal((daysBetween(config.together,event.day)+1)%100,0);
 }
});
test('coincident events are retained',()=>{
 const collision={...config,birthdays:[{name:'测试',day:'2000-06-28'}]};
 assert.equal(eventsForYear(collision,2026).filter(e=>e.day==='2026-06-28').length,2);
});
