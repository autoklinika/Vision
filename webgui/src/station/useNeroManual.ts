import {useEffect,useRef,useState} from 'react';
import {readNeroManual,sendNeroManual} from './transport';
import type {ManualAction,ManualStatus,ManualIntent} from './neroManualContract';
import type {TcpDeclaration,TcpIntent} from './neroTcpContract';

type Session={id:string;seq:number};
type ActiveInput={declaration:TcpDeclaration;intent:TcpIntent};
export function useNeroManual(instance:string,enabled:boolean){
 const [status,setStatus]=useState<ManualStatus|null>(null);
 const [approval,setApproval]=useState<string|null>(null);
 const [hasSession,setHasSession]=useState(false);
 const [busy,setBusy]=useState(false);
 const [notice,setNotice]=useState('');
 const session=useRef<Session|null>(null);
 const input=useRef<ActiveInput|null>(null);
 const interval=useRef<ReturnType<typeof setInterval>|null>(null);
 const pending=useRef(false);
 const generation=useRef(0);
 const statusEpoch=useRef(0);
 const active=useRef(enabled);active.current=enabled;
 const latest=useRef(status);latest.current=status;
 const stopTimer=()=>{
  generation.current++;input.current=null;
  if(interval.current!==null){clearInterval(interval.current);interval.current=null;}
 };
 function make(action:ManualAction,s:Session,axis:ActiveInput|null=null):ManualIntent{
  return {instanceId:instance,operationId:s.id,action,sequence:action==='ENABLE'?0:++s.seq,sentAt:Date.now()/1000,
   declaration:axis?.declaration??null,axis:axis?.intent.axis??null,direction:axis?.intent.direction??null};
 }
 const finish=(s:Session|null,action:'HOLD'|'CLOSE'|'RELEASE')=>{
  if(s)void sendNeroManual(make(action,s)).then(r=>{
   if(r.status!=='AVAILABLE'||!r.report.result.accepted)setNotice('Manual command unverified');
  });
 };
 function release(){
  const moving=input.current!==null;stopTimer();
  if(moving)finish(session.current,'RELEASE');
 }
 function close(){
  release();const s=session.current;session.current=null;setHasSession(false);setApproval(null);
  finish(s,'CLOSE');
 }
 function hold(){
  stopTimer();const s=session.current;session.current=null;setHasSession(false);
  finish(s,'HOLD');
 }
 function prepare(){
  if(active.current&&latest.current?.enableAvailable&&!session.current&&!busy)setApproval(crypto.randomUUID().replaceAll('-',''));
 }
 async function enable(){
  if(!approval||busy||!active.current||!latest.current?.enableAvailable)return;
  const s={id:approval,seq:0};statusEpoch.current++;setApproval(null);setBusy(true);setNotice('');
  try{
   const r=await sendNeroManual(make('ENABLE',s));
   if(r.status==='AVAILABLE'&&r.report.result.accepted&&active.current){
    statusEpoch.current++;session.current=s;setHasSession(true);
   }else{
    setNotice(r.status==='AVAILABLE'?r.report.result.reason:'Manual command unverified');
    if(r.status==='AVAILABLE'&&r.report.result.accepted)finish(s,'CLOSE');
   }
  }finally{setBusy(false);}
 }
 function start(declaration:TcpDeclaration,intent:TcpIntent){
  if(!active.current||!session.current||!latest.current?.jogAvailable||input.current!==null||
     declaration.linearMmS>latest.current.linearMax||declaration.angularDegS>latest.current.angularMax)return false;
  const token=++generation.current;
  input.current={declaration:{...declaration},intent:{...intent}};
  async function pulse(){
   if(token!==generation.current||!active.current||!session.current||!input.current||pending.current)return;
   pending.current=true;
   try{
    const r=await sendNeroManual(make('JOG',session.current,input.current));
    if(token===generation.current&&(r.status!=='AVAILABLE'||!r.report.result.accepted)){
     setNotice(r.status==='AVAILABLE'?r.report.result.reason:'Manual command unverified');release();
    }
   }finally{pending.current=false;}
  }
  void pulse();interval.current=setInterval(()=>void pulse(),80);return true;
 }
 useEffect(()=>{
  if(!enabled){setStatus(null);return;}
  let cancelled=false,timer:ReturnType<typeof setTimeout>;
  async function poll(){
   const epoch=statusEpoch.current;
   const r=await readNeroManual();
   if(cancelled)return;
   if(epoch!==statusEpoch.current){timer=setTimeout(()=>void poll(),100);return;}
   const v=r.status==='AVAILABLE'&&r.report.instanceId===instance?r.report.status:null;
   latest.current=v;setStatus(v);
   if(!v||['HOLD','FAULT','IDLE'].includes(v.state)){
    stopTimer();
    if(session.current){session.current=null;setHasSession(false);}
   }
   timer=setTimeout(()=>void poll(),350);
  }
  void poll();return()=>{cancelled=true;clearTimeout(timer);};
 },[instance,enabled]);
 useEffect(()=>{
  const lost=()=>{if(input.current)release();};
  const hide=()=>{if(document.hidden)lost();};
  window.addEventListener('blur',lost);document.addEventListener('visibilitychange',hide);
  return()=>{
   window.removeEventListener('blur',lost);document.removeEventListener('visibilitychange',hide);
   active.current=false;statusEpoch.current++;
   stopTimer();const s=session.current;session.current=null;
   // On unmount, stop/close is best effort; the owner lease is independent.
   finish(s,'CLOSE');
  };
 },[instance]);
 useEffect(()=>{if(!enabled){close();}},[enabled]);
 return {status,approval,hasSession,busy,notice,prepare,enable,cancelApproval:()=>setApproval(null),start,release,hold,close};
}
