/** Typed HTTP client and asynchronous task polling for the Agent API. */
import type {FormData,Mode,ModelSettings,Result,Status} from './types';

const base=(import.meta.env.VITE_API_BASE_URL||'/api').replace(/\/$/,'');

export class ApiError extends Error{constructor(message:string,public status=0){super(message)}}

async function request<T>(path:string,init?:RequestInit):Promise<T>{
  let r:Response;
  try{r=await fetch(`${base}${path}`,init)}
  catch{throw new ApiError('无法连接生成服务')}
  const body=await r.json().catch(()=>({}));
  if(!r.ok)throw new ApiError(body.detail?.message||body.detail||`请求失败 (${r.status})`,r.status);
  return body;
}

export const health=()=>request<{status:string}>('/health');

/** Loads effective provider settings; the API never returns secret key values. */
export const getModelSettings=()=>request<ModelSettings>('/settings/models');

/** Applies process-local provider settings until the FastAPI process restarts. */
export const saveModelSettings=(settings:ModelSettings)=>request<ModelSettings>('/settings/models',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(settings)});

type Accepted={task_id:string;poll_timeout_seconds?:number};
type TaskState={status:Status;result?:Result;error?:{message?:string};poll_timeout_seconds?:number};

function wait(ms:number,signal:AbortSignal){
  return new Promise<void>((resolve,reject)=>{
    const id=setTimeout(resolve,ms);
    signal.addEventListener('abort',()=>{clearTimeout(id);reject(new DOMException('Aborted','AbortError'))},{once:true});
  });
}

export async function generate(mode:Mode,data:FormData,signal:AbortSignal,onStatus:(s:Status)=>void):Promise<Result>{
  const path=mode==='copy'?'/generate':mode==='image'?'/generate/image':'/generate/all';
  const accepted=await request<Result|Accepted>(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal});
  if(!('task_id' in accepted))return accepted;
  onStatus('queued');
  const started=Date.now();
  let timeoutMs=(accepted.poll_timeout_seconds||120)*1000;
  while(Date.now()-started<timeoutMs){
    await wait(900,signal);
    const task=await request<TaskState>(`/tasks/${accepted.task_id}`,{signal});
    if(task.poll_timeout_seconds)timeoutMs=task.poll_timeout_seconds*1000;
    onStatus(task.status);
    if(task.status==='succeeded'&&task.result)return task.result;
    if(task.status==='failed')throw new ApiError(task.error?.message||'任务执行失败');
  }
  onStatus('timeout');
  throw new ApiError(`任务可能仍在服务端执行，可继续通过 /tasks/${accepted.task_id} 查询`);
}

export function mediaUrl(path?:string|null){
  if(!path)return null;
  if(/^https?:|^data:|^blob:/.test(path))return path;
  return path.startsWith('/media')?`${base.replace(/\/api$/,'')}${path}`:path;
}
