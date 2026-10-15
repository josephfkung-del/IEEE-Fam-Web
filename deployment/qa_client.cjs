const fs=require('fs'),vm=require('vm'),{webcrypto}=require('crypto');
const source=fs.readFileSync(__dirname+'/submission_form.js','utf8');
async function scenario(mode){
  let resets=0,posts=0;const keys=[];let formValues={family_name:'Mixed Signal',submitter_name:'QA',event_title:'QA',event_date:'2026-10-01',location_text:'Any venue',description:'Test',member_count:'4'};
  function element(){return {textContent:'',className:'',setAttribute(){},replaceChildren(){},append(){}}}
  const button={...element(),textContent:'Submit event →',disabled:false};
  const form={...element(),querySelector:()=>button,reset(){resets++}};
  const el={'#form':form,'#msg':element(),'#prev':element(),'#pic':element(),'#leaders':element()};
  class FormData{constructor(){this.v={...formValues}}get(k){return this.v[k]}[Symbol.iterator](){return Object.entries(this.v)[Symbol.iterator]()}}
  const memory=new Map();const ctx=vm.createContext({document:{querySelector:k=>el[k],createElement:element},FormData,crypto:webcrypto,TextEncoder,Uint8Array,
    sessionStorage:{getItem:k=>memory.get(k),setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)},
    fetch:async(path,options)=>{
      if(path!='/api/submissions')return {ok:true,json:async()=>({leaderboard:[]})};
      posts++;keys.push(options.headers['Idempotency-Key']);await new Promise(r=>setTimeout(r,10));
      if(mode==='network_error'&&posts===1)throw new Error('network down');
      if(mode==='server_error'||(mode==='retry'&&posts===1))return {ok:false,json:async()=>{throw new SyntaxError('non JSON response')}};
      return {ok:true,json:async()=>({ok:true})};
    }});
  vm.runInContext(source,ctx);vm.runInContext('photo="data:image/jpeg;base64,QA"',ctx);
  const submit=()=>vm.runInContext('f.onsubmit({preventDefault(){}})',ctx);
  const a=submit();if(mode==='double_click')await submit();await a;
  if(mode==='double_click'){if(posts!==1||resets!==1||button.disabled)throw Error('double click failed')}
  else{if(resets!==0||button.disabled||!el['#msg'].textContent.includes('retry'))throw Error('recovery failed');
    if(mode==='retry'||mode==='network_error'){await submit();if(keys[0]!==keys[1]||posts!==2||resets!==1)throw Error('retry failed')}}
  return {mode,posts,form_resets:resets,button_enabled:!button.disabled};
}
(async()=>{for(const mode of ['double_click','server_error','network_error','retry'])console.log('QA_CLIENT_PASS',JSON.stringify(await scenario(mode)))})().catch(e=>{console.error(e);process.exit(1)});
