import {useState} from 'react';

type Evidence = {columns:string[]; rows:unknown[][]; sql:string; evidence_hash:string};
type AgentResult = {thread_id:string; status:string; calls:number; errors:number; clarification:string;
  result:Evidence|Record<string,never>; trace:{tool:string;ok:boolean;error?:string;observation?:unknown}[]};

export default function AgentPanel(){
  const [question,setQuestion]=useState('What is paid booked revenue, before refunds?');
  const [apiKey,setApiKey]=useState('');
  const [result,setResult]=useState<AgentResult>();
  const [thread,setThread]=useState<string>();
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  async function submit(e:React.FormEvent){
    e.preventDefault(); setBusy(true); setError('');
    try{
      const response=await fetch('http://127.0.0.1:8081/agent/query',{
        method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+apiKey},
        body:JSON.stringify({question,...(thread?{thread_id:thread}:{})})});
      if(!response.ok)throw new Error('Request failed ('+response.status+'). Check the local server and API key.');
      const data:AgentResult=await response.json();setResult(data);
      setThread(data.status==='needs_clarification'?data.thread_id:undefined);
    }catch(err){setError(err instanceof Error?err.message:'Request failed');}
    finally{setBusy(false);}
  }
  const evidence=result?.result as Evidence|undefined;
  return <main>
    <h1>AskDB agent workbench</h1>
    <p>Synthetic commerce data. Inspect the tool trace before interpreting any answer.</p>
    <form onSubmit={submit}>
      <label>Local API key <input type="password" autoComplete="off" value={apiKey} onChange={e=>setApiKey(e.target.value)}/></label>
      <label>Analytics question<textarea maxLength={2000} required value={question} onChange={e=>setQuestion(e.target.value)}/></label>
      <button disabled={busy||apiKey.length<24}>{busy?'Running tools…':thread?'Send clarification':'Run agent'}</button>
      <button type="button" disabled={busy} onClick={()=>{setThread(undefined);setResult(undefined);setQuestion('');}}>New question</button>
    </form>
    {error&&<p role="alert">{error}</p>}
    {result&&<section aria-live="polite"><h2>{result.status.replace(/_/g,' ')}</h2>
      <p>{result.calls} model calls · {result.errors} recoverable errors</p>
      {result.status==='needs_clarification'&&<p>{result.clarification}</p>}
      {result.status==='completed'&&evidence?.columns&&<>
        <h3>Executed SQL</h3><pre style={{whiteSpace:'pre-wrap'}}>{evidence.sql}</pre>
        <div className="tablewrap"><table><thead><tr>{evidence.columns.map((col,i)=><th key={i}>{col}</th>)}</tr></thead>
          <tbody>{evidence.rows.map((row,i)=><tr key={i}>{row.map((value,j)=><td key={j}>{String(value??'NULL')}</td>)}</tr>)}</tbody></table></div>
        <p>Evidence SHA-256: <code>{evidence.evidence_hash}</code></p>
      </>}
      <h3>Tool trace</h3>{result.trace.map((event,i)=><details key={i}><summary>{i+1}. {event.tool}: {event.ok?'OK':'Rejected / failed'}</summary>
        <pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(event,null,2)}</pre></details>)}
    </section>}
  </main>;
}
