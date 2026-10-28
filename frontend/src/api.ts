import axios from 'axios';
export type QueryResult={question:string;sql:string;columns:string[];rows:Record<string,unknown>[];row_count:number};
export async function ask(question:string){return (await axios.post<QueryResult>('http://localhost:8000/query',{question})).data;}
