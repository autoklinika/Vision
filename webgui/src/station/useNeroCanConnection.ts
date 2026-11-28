import {useEffect,useRef,useState} from 'react';
import {readNeroCanConnection,connectNeroCan} from './transport';
import type {CanConnectionReport} from './neroCanConnectionContract';

export function useNeroCanConnection(instance:string,enabled:boolean){
 const [sample,setSample]=useState<{status:CanConnectionReport['status'];received:number}|null>(null);
 const [tick,setTick]=useState(()=>performance.now());
 const [busy,setBusy]=useState(false);
 const [notice,setNotice]=useState('');
 const pending=useRef(false);
 const active=useRef(enabled);active.current=enabled;
 const generation=useRef(0);
 useEffect(()=>{
  if(!enabled){setSample(null);return;}
  let cancelled=false,timer:ReturnType<typeof setTimeout>;
  const clock=setInterval(()=>setTick(performance.now()),200);
  async function poll(){
   const g=generation.current;
   const r=await readNeroCanConnection();
   if(cancelled)return;
   if(g===generation.current){
    const now=performance.now();setTick(now);
    setSample(r.status==='AVAILABLE'&&r.report.instanceId===instance?{status:r.report.status,received:now}:null);
   }
   timer=setTimeout(()=>void poll(),600);
  }
  void poll();return()=>{cancelled=true;clearInterval(clock);clearTimeout(timer);};
 },[instance,enabled]);
 const status=enabled&&sample&&tick-sample.received<=2000?sample.status:null;
 async function connect(){
  if(!active.current||pending.current||!status?.available)return;
  pending.current=true;generation.current++;setBusy(true);setNotice('');setSample(null);
  try{
   const r=await connectNeroCan({instanceId:instance,operationId:crypto.randomUUID().replaceAll('-',''),sentAt:Date.now()/1000});
   if(active.current)setNotice(r.status==='AVAILABLE'?r.report.result.reason:'CAN_CONNECT_UNVERIFIED');
  }finally{generation.current++;pending.current=false;setBusy(false);}
 }
 return {status,busy,notice,connect};
}
