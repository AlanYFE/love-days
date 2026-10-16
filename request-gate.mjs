// A response may update state only while it is the newest request in this session.
export function createRequestGate(){
 let generation=0,sequence=0;
 return {
  invalidate(){generation++;sequence++},
  begin(){const g=generation,s=++sequence;return ()=>g===generation&&s===sequence},
 };
}
