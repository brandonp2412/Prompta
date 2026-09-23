(()=>{
  const assistantSelector=__ASSISTANT_SELECTOR__;
  const messageRoleSelector=__MESSAGE_ROLE_SELECTOR__;
  const turnSelector=__TURN_SELECTOR__;
  const assistants=[...document.querySelectorAll(assistantSelector)];
  const latestAssistant=assistants.at(-1);
  const root=latestAssistant?.closest(turnSelector)
    ||document.querySelector('main')
    ||document.body;
  if(!root)return {ready:false,messages:[]};
  const found=[],seenObjects=new WeakSet(),seenArrays=new WeakSet();
  const add=messages=>{
    if(!Array.isArray(messages)||seenArrays.has(messages))return;
    seenArrays.add(messages);
    if(messages.some(message=>message&&typeof message==='object'&&message.content&&message.author)){
      found.push(...messages);
    }
  };
  const walk=(value,depth)=>{
    if(!value||depth>7||(typeof value!=='object'&&typeof value!=='function'))return;
    if(seenObjects.has(value))return;
    seenObjects.add(value);
    if(Array.isArray(value)){if(depth<=5)add(value);return;}
    let keys=[];
    try{keys=Object.keys(value);}catch{return;}
    for(const key of keys.slice(0,240)){
      if(['ref','_owner','return','child','sibling','stateNode','alternate'].includes(key))continue;
      let next;
      try{next=value[key];}catch{continue;}
      if(key==='messages')add(next);
      if(next&&depth<7&&(typeof next==='object'||typeof next==='function'))walk(next,depth+1);
    }
  };
  for(const node of [root,...root.querySelectorAll('*')]){
    let keys=[];
    try{
      keys=Object.getOwnPropertyNames(node).filter(name=>
        name.startsWith('__reactProps$')
        ||name.startsWith('__reactFiber$')
        ||name.startsWith('__reactContainer$')
      );
    }catch{}
    for(const key of keys)walk(node[key],0);
  }
  const seen=new Set(),messages=[];
  const trimString=value=>typeof value==='string'?value.slice(0,20000):value;
  for(const message of found){
    const id=String(message?.id||'');
    const dedupe=id||JSON.stringify([
      message?.author?.role,
      message?.recipient,
      message?.content?.content_type,
      message?.content?.text||''
    ]);
    if(seen.has(dedupe))continue;
    seen.add(dedupe);
    const metadata=message?.metadata||{};
    const invoked=metadata?.invoked_resource||null;
    const connectorName=metadata?.jit_plugin_data?.from_server?.body?.connector_name||null;
    const content=message?.content||{};
    messages.push({
      id,
      create_time:Number.isFinite(Number(message?.create_time))?Number(message.create_time):null,
      end_turn:typeof message?.end_turn==='boolean'?message.end_turn:null,
      role:String(message?.author?.role||message?.role||''),
      recipient:String(message?.recipient||''),
      content_type:String(content?.content_type||content?.type||''),
      text:trimString(content?.text||''),
      parts:Array.isArray(content?.parts)
        ?content.parts.slice(0,8).map(part=>trimString(part))
        :[],
      connector_tool_payload:trimString(metadata?.connector_tool_payload||''),
      reasoning_title:trimString(metadata?.reasoning_title||metadata?.reasoning_titles?.at?.(-1)||''),
      invoked_resource:invoked?{
        app_name:trimString(invoked?.app_name||''),
        resource_uri:trimString(invoked?.resource_uri||'')
      }:null,
      connector_name:trimString(connectorName||'')
    });
  }
  messages.sort((left,right)=>{
    const leftTime=Number.isFinite(Number(left.create_time))?Number(left.create_time):Number.POSITIVE_INFINITY;
    const rightTime=Number.isFinite(Number(right.create_time))?Number(right.create_time):Number.POSITIVE_INFINITY;
    return leftTime-rightTime;
  });
  return {
    ready:Boolean(messages.length||document.querySelector(messageRoleSelector)||root),
    href:location.href,
    title:document.title||'',
    messages
  };
})()
