// Optional Playwright check. API uses the explicitly scripted UI fixture.
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const cwd=new URL('..',import.meta.url);
const api=spawn(process.env.ASKDB_PYTHON||'python3',['devtools/browser-fixture.py'],{cwd,stdio:'inherit'});
const vite=spawn('npm',['run','dev','--','--host','127.0.0.1','--port','5173','--strictPort'],{cwd:new URL('../frontend/',import.meta.url),stdio:'ignore'});
let browser;
try{
  for(let i=0;i<100;i++){
    try{
      const a=await fetch('http://127.0.0.1:8081/health',{headers:{Authorization:'Bearer browser-fixture-only-'+'a'.repeat(32)}});
      const v=await fetch('http://127.0.0.1:5173');
      if(a.ok&&v.ok)break;
    }catch{}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,
    args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--disable-software-rasterizer','--single-process','--no-zygote']});
  const page=await browser.newPage({viewport:{width:1200,height:850}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://127.0.0.1:5173');
  await page.getByRole('heading',{name:'AskDB agent workbench'}).waitFor();
  await page.getByLabel('Local API key').fill('browser-fixture-only-'+'a'.repeat(32));
  await page.getByRole('button',{name:'Run agent'}).click();
  await page.getByRole('heading',{name:'completed',exact:true}).waitFor();
  if(await page.locator('td').first().textContent()!=='350')throw new Error('Incorrect UI evidence');
  await page.getByLabel('Analytics question').fill('Revenue?');
  await page.getByRole('button',{name:'Run agent'}).click();
  await page.getByText('Booked or net revenue?',{exact:true}).waitFor();
  await page.getByLabel('Analytics question').fill('How many paid orders?');
  await page.getByRole('button',{name:'Send clarification'}).click();
  await page.getByRole('heading',{name:'completed',exact:true}).waitFor();
  if(await page.locator('td').first().textContent()!=='3')throw new Error('Clarification result missing');
  await page.getByRole('button',{name:'New question'}).click();
  if(await page.getByLabel('Analytics question').inputValue()!=='')throw new Error('New question did not reset');
  await page.setViewportSize({width:390,height:844});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth))throw new Error('Mobile overflow');
  if(errors.length)throw new Error(errors.join('\n'));
  console.log('PASS: rendered workbench; API evidence; clarification follow-up; reset; mobile fit; no page errors. Scripted UI model.');
}finally{
  await browser?.close();api.kill('SIGTERM');vite.kill('SIGTERM');
}
