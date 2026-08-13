/** Model provider settings drawer for changing API endpoints without editing files. */
import{useEffect,useState}from'react';
import{CheckCircle2,KeyRound,LoaderCircle,Save,Settings2,X}from'lucide-react';
import{getModelSettings,saveModelSettings}from'./api';
import type{ModelSettings,ProviderSettings}from'./types';

const empty:ModelSettings={
  text:{backend:'mock',model:'',api_url:'',api_key_configured:false,api_key:'',managed_by_env:false},
  image:{backend:'disabled',model:'',api_url:'',api_key_configured:false,api_key:''},
  video:{backend:'disabled',model:'',api_url:'',query_url:'',api_key_configured:false,api_key:''},
};
type Kind=keyof ModelSettings;

/** Renders one provider's backend, endpoint, model, and write-only credential fields. */
function ProviderForm({kind,value,onChange}:{kind:Kind;value:ProviderSettings;onChange:(v:ProviderSettings)=>void}){
  const labels={text:'Text model',image:'Image model',video:'Video model'};
  const options=kind==='text'?['mock','api','vllm']:['disabled','mock','api'];
  const readOnly=Boolean(value.managed_by_env);
  const showApiFields=value.backend==='api'&&!readOnly;
  const showQueryUrl=kind==='video'&&showApiFields;
  return <section className="provider-form">
    <div className="provider-title">
      <div><span>{kind.toUpperCase()}</span><h3>{labels[kind]}</h3></div>
      {readOnly?<small>Managed by environment</small>:value.api_key_configured&&<small><CheckCircle2 size={13}/> Key configured</small>}
    </div>
    <div className="settings-grid">
      <label><span>Backend</span>{readOnly?<input value={value.backend} readOnly/>:<select value={value.backend} onChange={e=>onChange({...value,backend:e.target.value})}>{options.map(x=><option key={x}>{x}</option>)}</select>}</label>
      <label><span>Model / endpoint ID</span><input value={value.model} readOnly={readOnly} onChange={e=>onChange({...value,model:e.target.value})} placeholder={kind==='text'?'model-name':'ep-xxxxxxxx'}/></label>
      {showApiFields&&<label className="full"><span>{kind==='video'?'Create URL':'API base URL'}</span><input value={value.api_url} onChange={e=>onChange({...value,api_url:e.target.value})} placeholder="https://..."/></label>}
      {showQueryUrl&&<label className="full"><span>Query URL</span><input value={value.query_url||''} onChange={e=>onChange({...value,query_url:e.target.value})} placeholder="https://..."/></label>}
      {showApiFields&&<label className="full"><span>API Key</span><div className="secret-input"><KeyRound size={15}/><input type="password" autoComplete="new-password" value={value.api_key||''} onChange={e=>onChange({...value,api_key:e.target.value})} placeholder={value.api_key_configured?'Leave blank to keep current key':'Enter API key'}/></div></label>}
    </div>
  </section>;
}

/** Loads settings on open and saves all providers atomically through FastAPI. */
export default function SettingsPanel({open,onClose}:{open:boolean;onClose:()=>void}){
  const[settings,setSettings]=useState<ModelSettings>(empty);
  const[loading,setLoading]=useState(false);
  const[saving,setSaving]=useState(false);
  const[message,setMessage]=useState('');
  useEffect(()=>{if(!open)return;document.body.style.overflow='hidden';setLoading(true);setMessage('');getModelSettings().then(setSettings).catch(e=>setMessage(e.message)).finally(()=>setLoading(false));return()=>{document.body.style.overflow=''}},[open]);
  if(!open)return null;
  const update=(kind:Kind,value:ProviderSettings)=>setSettings(s=>({...s,[kind]:value}));
  const save=async()=>{setSaving(true);setMessage('');try{const next=await saveModelSettings(settings);setSettings(next);setMessage('Settings applied for this server session.')}catch(e){setMessage((e as Error).message)}finally{setSaving(false)}};
  return <div className="settings-overlay" role="dialog" aria-modal="true" aria-label="Model settings">
    <button className="settings-backdrop" aria-label="Close settings" onClick={onClose}/>
    <aside className="settings-drawer">
      <header className="settings-header"><div><span>RUNTIME CONFIG</span><h2><Settings2 size={20}/> Model settings</h2></div><button className="icon-btn" title="Close" onClick={onClose}><X size={18}/></button></header>
      <p className="settings-note">Keys are sent only to the local API process and are never returned or stored in this browser. Settings reset when FastAPI restarts.</p>
      {loading?<div className="settings-loading"><LoaderCircle className="spin"/> Loading settings...</div>:<div className="settings-content">{(['text','image','video']as Kind[]).map(kind=><ProviderForm key={kind} kind={kind} value={settings[kind]} onChange={v=>update(kind,v)}/>)}</div>}
      <footer className="settings-footer">{message&&<span>{message}</span>}<button className="generate" disabled={loading||saving} onClick={save}>{saving?<LoaderCircle className="spin" size={17}/>:<Save size={17}/>} Save settings</button></footer>
    </aside>
  </div>;
}
