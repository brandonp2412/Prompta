__MESSAGE_DISCOVERY__
__REACT_FALLBACK_ADAPTER__
const promptaTranscriptEngine=(()=>{
  const fallbackUses=[];
  const fallbackAttempt=result=>({
    allowed:result.allowed,
    used:result.used,
    available:result.available,
    provenance:result.provenance,
    reason:result.reason,
    property_names:result.property_names,
    error:result.error
  });
  const inspectReact=(root,reason,{maxDepth=7,maxKeys=240}={})=>{
    const result=reactFallback.inspect(root,{allow:true,reason,maxDepth,maxKeys});
    fallbackUses.push(fallbackAttempt(result));
    return result;
  };
  const reactMessages=(root,reason,options={})=>inspectReact(root,reason,options).messages;
  const hasVisibleAssistantText=(agent,messages)=>{
    const normalise=value=>(value||'').replace(/\s+/g,' ').trim();
    const visibleAgentText=normalise(agent?.innerText||agent?.textContent||'');
    if(!visibleAgentText)return false;
    return messages.some(message=>{
      const role=String(message?.author?.role||message?.role||'');
      const recipient=String(message?.recipient||'');
      const content=message?.content||{};
      const contentType=String(content?.content_type||content?.type||'');
      if(role!=='assistant'||(recipient&&recipient!=='all')||(
        contentType!=='text'&&contentType!=='multimodal_text'
      ))return false;
      const parts=Array.isArray(content?.parts)
        ?content.parts.filter(part=>typeof part==='string'&&part.trim())
        :[];
      const sourceText=normalise(parts.length?parts.join(' '):String(content?.text||''));
      return Boolean(sourceText&&visibleAgentText.includes(sourceText));
    });
  };
  const safeJsonValue=value=>{try{return JSON.parse(JSON.stringify(value));}catch{return null;}};
  const sanitiseSourceEvent=(message,{stringLimit=0,partsLimit=0}={})=>{
    const clipString=value=>typeof value==='string'&&stringLimit>0
      ?value.slice(0,stringLimit)
      :value;
    const content=message?.content||{};
    const metadata=message?.metadata||{};
    const invoked=metadata?.invoked_resource||null;
    const connectorName=metadata?.jit_plugin_data?.from_server?.body?.connector_name||null;
    const reasoningTitles=(Array.isArray(metadata?.reasoning_titles)
      ?metadata.reasoning_titles.filter(value=>typeof value==='string')
      :[]
    ).map(clipString);
    const rawParts=safeJsonValue(content?.parts||[]);
    const parts=Array.isArray(rawParts)&&partsLimit>0
      ?rawParts.slice(0,partsLimit).map(clipString)
      :rawParts;
    return {
      id:String(message?.id||''),
      parent_id:String(message?.parent_id||''),
      create_time:Number.isFinite(Number(message?.create_time))?Number(message.create_time):null,
      update_time:Number.isFinite(Number(message?.update_time))?Number(message.update_time):null,
      end_turn:typeof message?.end_turn==='boolean'?message.end_turn:null,
      status:clipString(String(message?.status||'')),
      role:clipString(String(message?.author?.role||message?.role||'')),
      recipient:clipString(String(message?.recipient||'')),
      content_type:clipString(String(content?.content_type||content?.type||'')),
      text:typeof content?.text==='string'?clipString(content.text):'',
      parts,
      connector_tool_payload:typeof metadata?.connector_tool_payload==='string'
        ?clipString(metadata.connector_tool_payload)
        :'',
      reasoning_title:clipString(String(
        metadata?.reasoning_title||reasoningTitles.at(-1)||''
      )),
      reasoning_titles:reasoningTitles,
      invoked_resource:invoked?safeJsonValue({
        app_name:clipString(String(invoked?.app_name||'')),
        resource_uri:clipString(String(invoked?.resource_uri||''))
      }):null,
      connector_name:clipString(String(connectorName||'')),
      model_slug:clipString(String(metadata?.model_slug||metadata?.default_model_slug||'')),
      request_id:clipString(String(metadata?.request_id||metadata?.requestId||'')),
      attachments:safeJsonValue(metadata?.attachments??content?.attachments??[]),
      citations:safeJsonValue(metadata?.citations??content?.citations??[]),
      content_references:safeJsonValue(
        metadata?.content_references??content?.content_references??[]
      )
    };
  };
  const latestAssistantRoot=()=>{
    const assistants=[...document.querySelectorAll(assistantSelector)];
    const latestAssistant=assistants.at(-1);
    return turnRoot(latestAssistant)
      ||document.querySelector('main')
      ||document.body;
  };
  const reactSnapshot=(root,reason,options={})=>{
    if(!root)return {ready:false,messages:[]};
    const fallback=inspectReact(root,reason);
    const messages=fallback.messages.map(message=>sanitiseSourceEvent(message,options));
    return {
      ready:Boolean(messages.length||document.querySelector(messageRoleSelector)||root),
      href:location.href,
      title:document.title||'',
      messages,
      react_fallback:fallbackAttempt(fallback)
    };
  };
  const reactFallbackSummary=()=>({
    provenance:'react-private-properties',
    used:fallbackUses.some(result=>result.used),
    attempts:fallbackUses
  });
  return {
    hasVisibleAssistantText,
    inspectReact,
    latestAssistantRoot,
    reactFallbackSummary,
    reactMessages,
    reactSnapshot,
    sanitiseSourceEvent
  };
})();
