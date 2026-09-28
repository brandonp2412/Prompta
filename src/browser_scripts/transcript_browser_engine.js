/*__MESSAGE_DISCOVERY__*/
/*__REACT_FALLBACK_ADAPTER__*/
const promptaTranscriptEngine=(()=>{
  const fallbackUses=[];
  const fallbackDeadline=performance.now()+2500;
  const fallbackAttempt=result=>({
    allowed:result.allowed,
    used:result.used,
    available:result.available,
    provenance:result.provenance,
    reason:result.reason,
    property_names:result.property_names,
    truncated:result.truncated,
    scanned_nodes:result.scanned_nodes,
    scanned_objects:result.scanned_objects,
    error:result.error
  });
  const inspectReact=(root,reason,{maxDepth=7,maxKeys=240}={})=>{
    const maxMillis=Math.max(1,fallbackDeadline-performance.now());
    const result=reactFallback.inspect(root,{allow:true,reason,maxDepth,maxKeys,maxMillis});
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
  const referencedText=(node,attributeName)=>String(node?.getAttribute?.(attributeName)||'')
    .split(/\s+/)
    .filter(Boolean)
    .map(id=>document.getElementById(id)?.textContent||'')
    .join(' ')
    .replace(/\s+/g,' ')
    .trim();
  const labelledByText=node=>referencedText(node,'aria-labelledby');
  const describedByText=node=>referencedText(node,'aria-describedby');
  const interactiveControlSelector=[
    'button',
    'summary',
    'input[type="button"]',
    'input[type="submit"]',
    '[role="button"]',
    '[role="menuitem"]',
    '[aria-controls]',
    '[aria-expanded]',
    '[aria-pressed]',
    '[tabindex]:not([tabindex="-1"])'
  ].join(',');
  const interactiveControls=root=>root?.querySelectorAll
    ?[...root.querySelectorAll(interactiveControlSelector)]
    :[];
  const isInteractiveControl=node=>Boolean(node?.matches?.(interactiveControlSelector));
  const isStopControl=node=>{
    if(!isInteractiveControl(node))return false;
    const attributeText=[...(node.attributes||[])]
      .filter(attribute=>(
        attribute.name==='aria-label'
        ||attribute.name==='title'
        ||attribute.name==='data-testid'
        ||attribute.name.startsWith('data-')
      ))
      .map(attribute=>attribute.name+' '+attribute.value)
      .join(' ');
    const descendantSemanticText=node.querySelectorAll
      ?[...node.querySelectorAll('*')].flatMap(child=>[
        child.getAttribute?.('aria-label')||'',
        child.getAttribute?.('title')||'',
        child.getAttribute?.('data-icon')||'',
        child.getAttribute?.('data-testid')||'',
        child.getAttribute?.('data-action')||'',
        child.getAttribute?.('data-state')||''
      ]).join(' ')
      :'';
    const label=[
      node.getAttribute?.('aria-label')||'',
      labelledByText(node),
      describedByText(node),
      node.getAttribute?.('title')||'',
      node.textContent||'',
      attributeText,
      descendantSemanticText
    ].join(' ').replace(/[-_]+/g,' ');
    return /\b(?:stop(?:\s+(?:answering|generating|generation|response|responding))?|cancel\s+(?:generation|response))\b/i.test(label);
  };
  const isTurnActionControl=node=>{
    if(!isInteractiveControl(node))return false;
    const attributes=[...(node.attributes||[])];
    const semanticTokens=value=>new Set(
      String(value||'')
        .toLowerCase()
        .replace(/[_:]+/g,'-')
        .split(/[^a-z0-9]+/)
        .filter(Boolean)
    );
    const actionTokens=new Set([
      'copy','regenerate','retry','read','aloud','thumb','up','down',
      'good','bad','feedback','response','message','turn','action'
    ]);
    const semanticAction=attributes.some(attribute=>{
      const tokens=new Set([
        ...semanticTokens(attribute.name),
        ...semanticTokens(attribute.value)
      ]);
      return (tokens.has('turn')&&tokens.has('action'))
        ||(tokens.has('message')&&tokens.has('action'))
        ||([...tokens].some(token=>actionTokens.has(token))
          &&['data-action','data-testid','data-state','name'].includes(
            String(attribute.name||'').toLowerCase()
          ));
    });
    if(semanticAction)return true;
    const descendantSemanticText=node.querySelectorAll
      ?[...node.querySelectorAll('*')].flatMap(child=>[
        child.getAttribute?.('aria-label')||'',
        child.getAttribute?.('title')||'',
        child.getAttribute?.('data-icon')||'',
        child.getAttribute?.('data-testid')||'',
        child.getAttribute?.('data-action')||''
      ]).join(' ')
      :'';
    const actionLabel=value=>{
      const label=String(value||'').replace(/[-_]+/g,' ').replace(/\s+/g,' ').trim();
      if(!label)return false;
      return /\b(?:copy|regenerate|retry|read\s+aloud|good\s+(?:response|answer)|bad\s+(?:response|answer)|thumbs?\s+(?:up|down))\b/i.test(label);
    };
    return [
      node.getAttribute?.('aria-label')||'',
      labelledByText(node),
      describedByText(node),
      node.getAttribute?.('title')||'',
      node.textContent||'',
      descendantSemanticText
    ].some(actionLabel);
  };
  const latestAssistantRoot=()=>{
    const latestAssistant=authorNodes('assistant').at(-1)||null;
    return turnRoot(latestAssistant)
      ||document.querySelector('main,[role="main"]')
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
    interactiveControls,
    isInteractiveControl,
    isStopControl,
    isTurnActionControl,
    latestAssistantRoot,
    reactFallbackSummary,
    reactMessages,
    reactSnapshot,
    sanitiseSourceEvent
  };
})();
