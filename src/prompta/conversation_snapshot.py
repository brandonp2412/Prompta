from __future__ import annotations

import json
from typing import Any

from .chatgpt_dom import (
    ASSISTANT_MESSAGE_SELECTOR,
    MARKDOWN_SELECTOR,
    MESSAGE_ROLE_SELECTOR,
    STOP_BUTTON_SELECTOR,
    STREAMING_SELECTOR,
    TURN_SELECTOR,
)

CONVERSATION_SNAPSHOT_SCRIPT = """JSON.stringify((()=>{
  const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
  const normalise=value=>(value||'').replace(/\\s+/g,' ').trim();
  const hash=value=>{let h=2166136261;for(const ch of value){h^=ch.charCodeAt(0);h=Math.imul(h,16777619);}return (h>>>0).toString(36);};
  const messageRoleSelector=__MESSAGE_ROLE_SELECTOR__;
  const assistantSelector=__ASSISTANT_SELECTOR__;
  const turnSelector=__TURN_SELECTOR__;
  const markdownSelector=__MARKDOWN_SELECTOR__;
  const stopSelector=__STOP_SELECTOR__;
  const streamingSelector=__STREAMING_SELECTOR__;
  const messageText=root=>{
    if(!root)return '';
    const clone=root.cloneNode(true);
    clone.querySelectorAll('button,[role="button"]').forEach(node=>node.remove());
    const text=(clone.textContent||'').trim();
    const actionSuffix=['Show moreShow less','Show lessShow more'].find(suffix=>text.endsWith(suffix));
    return (actionSuffix?text.slice(0,-actionSuffix.length):text).trim();
  };
  const markdownText=root=>{
    const walk=node=>{
      if(node.nodeType===Node.TEXT_NODE)return node.textContent||'';
      if(node.nodeType!==Node.ELEMENT_NODE)return '';
      const tag=node.tagName.toLowerCase();
      const children=()=>[...node.childNodes].map(walk).join('');
      if(tag==='br')return '\\n';
      if(/^h[1-6]$/.test(tag))return '#'.repeat(Number(tag[1]))+' '+children().trim()+'\\n\\n';
      if(tag==='p')return children().trim()+'\\n\\n';
      if(tag==='strong'||tag==='b')return '**'+children()+'**';
      if(tag==='em'||tag==='i')return '*'+children()+'*';
      if(tag==='del'||tag==='s')return '~~'+children()+'~~';
      if(tag==='code'&&node.parentElement?.tagName.toLowerCase()!=='pre')return '`'+children()+'`';
      if(tag==='pre'){
        const code=node.querySelector('code')||node;
        const className=code.getAttribute('class')||'';
        const language=className.match(/language-([\\w+-]+)/)?.[1]||'';
        return '```'+language+'\\n'+(code.textContent||'').replace(/\\n$/,'')+'\\n```\\n\\n';
      }
      if(tag==='a'){
        const href=node.getAttribute('href')||'';
        const label=children().trim()||href;
        return /^https?:\\/\\//i.test(href)?'['+label+']('+href+')':label;
      }
      if(tag==='ul'||tag==='ol'){
        const ordered=tag==='ol';
        return [...node.children].filter(child=>child.tagName.toLowerCase()==='li').map((child,index)=>{
          const body=[...child.childNodes].filter(part=>!(part.nodeType===Node.ELEMENT_NODE&&['ul','ol'].includes(part.tagName.toLowerCase()))).map(walk).join('').trim();
          const nested=[...child.children].filter(part=>['ul','ol'].includes(part.tagName.toLowerCase())).map(walk).join('').trimEnd();
          const prefix=ordered?(index+1)+'. ':'- ';
          return prefix+body+(nested?'\\n'+nested.split('\\n').map(line=>line?'  '+line:line).join('\\n'):'');
        }).join('\\n')+'\\n\\n';
      }
      if(tag==='blockquote')return children().trim().split('\\n').map(line=>'> '+line).join('\\n')+'\\n\\n';
      if(tag==='hr')return '---\\n\\n';
      if(tag==='li')return children();
      if(tag==='div'||tag==='section'||tag==='article')return children();
      return children();
    };
    return walk(root).replace(/\\n{3,}/g,'\\n\\n').trim();
  };
  const toolSelector='[data-tool-call-id],[data-tool-name]';
  const toolNoise=/^(?:Open tool call list|Close tool call list|Tool|Tool call|Expand|Collapse|cot-v5-[\\w-]+)$/i;
  const cleanToolName=value=>{const text=(value||'').replace(/\\s+/g,' ').trim();return text&&!toolNoise.test(text)?text:'';};
  const reactMessages=agent=>{
    const found=[],seenObjects=new WeakSet(),seenArrays=new WeakSet();
    const add=messages=>{
      if(!Array.isArray(messages)||seenArrays.has(messages))return;
      seenArrays.add(messages);
      if(messages.some(message=>message&&typeof message==='object'&&message.content&&message.author))found.push(...messages);
    };
    const walk=(value,depth)=>{
      if(!value||depth>6||(typeof value!=='object'&&typeof value!=='function'))return;
      if(seenObjects.has(value))return;
      seenObjects.add(value);
      if(Array.isArray(value)){if(depth<=4)add(value);return;}
      let keys=[];
      try{keys=Object.keys(value);}catch{return;}
      for(const key of keys.slice(0,220)){
        if(['ref','_owner','return','child','sibling','stateNode','alternate'].includes(key))continue;
        let next;
        try{next=value[key];}catch{continue;}
        if(key==='messages')add(next);
        if(next&&depth<6&&(typeof next==='object'||typeof next==='function'))walk(next,depth+1);
      }
    };
    for(const node of [agent,...agent.querySelectorAll('*')]){
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
    const unique=[],seen=new Set();
    for(const message of found){
      const key=message?.id||JSON.stringify([
        message?.author?.role,
        message?.recipient,
        message?.content?.content_type,
        message?.content?.text||''
      ]);
      if(seen.has(key))continue;
      seen.add(key);
      unique.push(message);
    }
    const messageTime=message=>{
      const value=Number(message?.create_time);
      return Number.isFinite(value)?value:Number.POSITIVE_INFINITY;
    };
    const positionById=new Map();
    unique.forEach((message,index)=>{
      const id=String(message?.id||'').trim();
      if(id)positionById.set(id,index);
    });
    const indegree=unique.map(()=>0);
    const children=new Map();
    unique.forEach((message,index)=>{
      const parentId=String(message?.parent_id||'').trim();
      const parentIndex=positionById.get(parentId);
      if(parentIndex===undefined||parentIndex===index)return;
      indegree[index]+=1;
      const descendants=children.get(parentIndex)||[];
      descendants.push(index);
      children.set(parentIndex,descendants);
    });
    const priority=(left,right)=>{
      const leftTime=messageTime(unique[left]);
      const rightTime=messageTime(unique[right]);
      if(leftTime!==rightTime)return leftTime<rightTime?-1:1;
      return left-right;
    };
    const ready=indegree.map((degree,index)=>degree===0?index:null)
      .filter(index=>index!==null);
    const ordered=[];
    while(ready.length){
      ready.sort(priority);
      const index=ready.shift();
      ordered.push(index);
      for(const child of children.get(index)||[]){
        indegree[child]-=1;
        if(indegree[child]===0)ready.push(child);
      }
    }
    if(ordered.length!==unique.length){
      const seen=new Set(ordered);
      ordered.push(...unique.map((_,index)=>index).filter(index=>!seen.has(index)).sort(priority));
    }
    return ordered.map(index=>unique[index]);
  };
  const reactHasVisibleAssistantText=agent=>{
    const visibleAgentText=normalise(agent?.innerText||agent?.textContent||'');
    if(!visibleAgentText)return false;
    return reactMessages(agent).some(message=>{
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
  const sanitiseSourceEvent=message=>{
    const content=message?.content||{};
    const metadata=message?.metadata||{};
    const invoked=metadata?.invoked_resource||null;
    const connectorName=metadata?.jit_plugin_data?.from_server?.body?.connector_name||null;
    const reasoningTitles=Array.isArray(metadata?.reasoning_titles)
      ?metadata.reasoning_titles.filter(value=>typeof value==='string')
      :[];
    return {
      id:String(message?.id||''),
      parent_id:String(message?.parent_id||''),
      create_time:Number.isFinite(Number(message?.create_time))?Number(message.create_time):null,
      update_time:Number.isFinite(Number(message?.update_time))?Number(message.update_time):null,
      end_turn:typeof message?.end_turn==='boolean'?message.end_turn:null,
      status:String(message?.status||''),
      role:String(message?.author?.role||message?.role||''),
      recipient:String(message?.recipient||''),
      content_type:String(content?.content_type||content?.type||''),
      text:typeof content?.text==='string'?content.text:'',
      parts:safeJsonValue(content?.parts||[]),
      connector_tool_payload:typeof metadata?.connector_tool_payload==='string'?metadata.connector_tool_payload:'',
      reasoning_title:String(metadata?.reasoning_title||reasoningTitles.at(-1)||''),
      reasoning_titles:reasoningTitles,
      invoked_resource:invoked?safeJsonValue({
        app_name:invoked?.app_name||'',
        resource_uri:invoked?.resource_uri||''
      }):null,
      connector_name:String(connectorName||''),
      model_slug:String(metadata?.model_slug||metadata?.default_model_slug||''),
      request_id:String(metadata?.request_id||metadata?.requestId||''),
      attachments:safeJsonValue(metadata?.attachments??content?.attachments??[]),
      citations:safeJsonValue(metadata?.citations??content?.citations??[]),
      content_references:safeJsonValue(metadata?.content_references??content?.content_references??[])
    };
  };
  const reactToolBlocks=agent=>{
    const messages=reactMessages(agent);
    if(!messages.length)return [];
    const parsedText=message=>{
      const text=message?.content?.text;
      if(typeof text!=='string'||!text.trim())return null;
      try{return JSON.parse(text);}catch{return null;}
    };
    const resourcePath=message=>String(
      message?.metadata?.invoked_resource?.resource_uri||''
    );
    const pathAction=path=>String(path||'').split('/').filter(Boolean).at(-1)||'';
    const pathConnector=path=>{
      const parts=String(path||'').split('/').filter(Boolean);
      const first=parts[0]||'';
      return first&&!/^asdk_app_/i.test(first)&&!/^link_/i.test(first)?first:'';
    };
    const connectorNames=messages.flatMap(message=>[
      message?.metadata?.jit_plugin_data?.from_server?.body?.connector_name,
      message?.metadata?.invoked_resource?.app_name,
      pathConnector(resourcePath(message))
    ]).filter(Boolean);
    const fallbackConnector=connectorNames.at(-1)||'';
    const blocks=[];
    const reasoningTitle=message=>String(
      message?.metadata?.reasoning_title
      ||message?.metadata?.reasoning_titles?.at?.(-1)
      ||''
    ).trim();
    const add=(name,action,summary,args,status,duration,error,createdAt)=>{
      const label=[name,action].filter(Boolean).join(' · ')||'tool';
      const detail={};
      if(summary)detail.summary=summary;
      if(args&&typeof args==='object')detail.arguments=args;
      else if(args!=null)detail.arguments=args;
      if(status)detail.status=status;
      if(Number.isFinite(duration))detail.duration_ms=duration;
      if(error)detail.error=typeof error==='string'?error:JSON.stringify(error);
      if(Number.isFinite(Number(createdAt))&&Number(createdAt)>0)detail.created_at=Number(createdAt);
      const body=Object.keys(detail).length?JSON.stringify(detail,null,2):'Called tool';
      const block='```tool:'+label+'\\n'+body+'\\n```';
      blocks.push(block);
    };
    const invocations=[];
    for(const [index,message] of messages.entries()){
      const parsed=parsedText(message);
      if(!parsed||typeof parsed!=='object')continue;
      const path=typeof parsed.path==='string'?parsed.path:'';
      const action=parsed.appContext?.actionName
        ||(typeof parsed.tool==='string'?parsed.tool.split('.').at(-1):'')
        ||pathAction(path);
      const name=parsed.appContext?.appName
        ||message?.metadata?.invoked_resource?.app_name
        ||pathConnector(path)
        ||fallbackConnector;
      const args=parsed.arguments??parsed.args;
      const summary=reasoningTitle(message);
      if(message?.recipient==='api_tool.call_tool'||path){
        invocations.push({index,name,action,args,path,summary,createdAt:Number(message?.create_time)});
      }
      if(parsed.type==='mcpToolCall'||parsed.appContext||parsed.arguments){
        const prior=[...invocations].reverse().find(candidate=>
          candidate.index<=index&&(!action||!candidate.action||candidate.action===action)
        );
        add(name,action,summary||prior?.summary||'',args,parsed.status,parsed.durationMs,parsed.error,prior?.createdAt||Number(message?.create_time));
      }
    }
    if(blocks.length)return blocks;

    let completed=0;
    for(const [index,message] of messages.entries()){
      const path=resourcePath(message);
      if(!path)continue;
      const action=pathAction(path);
      const name=message?.metadata?.invoked_resource?.app_name
        ||pathConnector(path)
        ||fallbackConnector;
      const invocation=[...invocations].reverse().find(candidate=>
        candidate.index<index&&(
          !action||!candidate.action||candidate.action===action
        )
      );
      add(
        name||invocation?.name||'',
        action||invocation?.action||'',
        invocation?.summary||reasoningTitle(message),
        invocation?.args,
        'completed',
        null,
        null,
        Number(message?.create_time)||invocation?.createdAt
      );
      completed+=1;
    }
    if(completed)return blocks;

    for(const invocation of invocations){
      add(
        invocation.name||fallbackConnector,
        invocation.action,
        invocation.summary,
        invocation.args,
        'running',
        null,
        null,
        invocation.createdAt
      );
    }
    return blocks;
  };
  const toolBlocks=agent=>{
    const structuredBlocks=reactToolBlocks(agent);
    if(structuredBlocks.length)return structuredBlocks;
    const currentRows=[...agent.querySelectorAll('span[class~="group/tool-message"]')];
    const currentBlocks=currentRows.map(node=>{
      const lines=(node.innerText||node.textContent||'').split(/\\n+/)
        .map(line=>line.trim())
        .filter(Boolean);
      const name=lines.map(cleanToolName).find(line=>!/^Called tool$/i.test(line))||'';
      const body=name?'':'Called tool';
      return '```tool:'+(name||'tool')+'\\n'+body+'\\n```';
    });
    const legacyBlocks=[...new Set([
      ...agent.querySelectorAll(toolSelector)
    ])].filter(node=>!node.closest('span[class~="group/tool-message"]')&&!node.querySelector(toolSelector)).map(node=>{
      const name=[
        node.getAttribute('data-tool-name'),
        node.getAttribute('aria-label'),
        node.getAttribute('title')
      ].map(cleanToolName).find(Boolean)||'';
      const detail=(node.innerText||node.textContent||'').split(/\\n+/)
        .map(line=>line.trim())
        .filter(line=>line&&cleanToolName(line))
        .join('\\n').trim().slice(0,16000);
      const body=normalise(detail)===normalise(name)?'':detail;
      if(!body&&!name)return '';
      const label=name||'tool';
      return '```tool:'+label+'\\n'+body+'\\n```';
    }).filter(Boolean);
    return [...legacyBlocks,...currentBlocks];
  };
  const collapseStreamingTextParts=parts=>{
    const collapsed=[];
    for(const rawPart of parts){
      const part=String(rawPart||'').trim();
      if(!part)continue;
      const previous=collapsed.at(-1)||'';
      const previousIsTool=previous.startsWith('```tool:');
      const currentIsTool=part.startsWith('```tool:');
      if(previous&&!previousIsTool&&!currentIsTool){
        const previousNormalised=normalise(previous);
        const currentNormalised=normalise(part);
        const sameStream=previousNormalised&&currentNormalised&&(
          currentNormalised===previousNormalised
          ||currentNormalised.startsWith(previousNormalised)
          ||previousNormalised.startsWith(currentNormalised)
        );
        if(sameStream){
          if(currentNormalised.length>=previousNormalised.length){
            collapsed[collapsed.length-1]=part;
          }
          continue;
        }
      }
      collapsed.push(part);
    }
    return collapsed;
  };
  const networkErrorNoise=/a network error occurred\\.?\\s*please check your connection and try again\\.?\\s*if this issue persists please contact us through our help center at help\\.openai\\.com\\.?/i;
  const assistantUiNoise=/^(?:connection interrupted\\.?(?:\\s*waiting for (?:the )?complete answer\\.?)?|waiting for (?:the )?complete answer\\.?|message delivery timed out\\.?\\s*please try again\\.?|a network error occurred\\.?(?:\\s*please check your connection and try again\\.?(?:\\s*if this issue persists please contact us through our help center at help\\.openai\\.com\\.?)?)?)$/i;
  const cleanAssistantText=text=>String(text||'').replace(networkErrorNoise,'').split(/\\n+/)
    .map(line=>line.trim())
    .filter(line=>line&&!assistantUiNoise.test(line))
    .join('\\n').trim();
  const reactOrderedContent=agent=>{
    const messages=reactMessages(agent);
    if(!messages.length)return '';
    const tools=reactToolBlocks(agent);
    const parsedByIndex=messages.map(message=>{
      const text=message?.content?.text;
      if(typeof text!=='string'||!text.trim())return null;
      try{return JSON.parse(text);}catch{return null;}
    });
    const hasCompletedWrappers=parsedByIndex.some(parsed=>Boolean(
      parsed&&typeof parsed==='object'&&(
        parsed.type==='mcpToolCall'||parsed.appContext||parsed.arguments
      )
    ));
    const textEntries=[];
    for(const [index,message] of messages.entries()){
      const role=String(message?.author?.role||message?.role||'');
      const recipient=String(message?.recipient||'');
      const content=message?.content||{};
      const contentType=String(content?.content_type||content?.type||'');
      if(role!=='assistant'||(recipient&&recipient!=='all')||(
        contentType!=='text'&&contentType!=='multimodal_text'
      ))continue;
      const textParts=Array.isArray(content?.parts)
        ?content.parts.filter(part=>typeof part==='string'&&part.trim())
        :[];
      const visibleText=cleanAssistantText(
        textParts.length?textParts.join('\\n'):String(content?.text||'')
      );
      if(visibleText)textEntries.push({index,message,content:visibleText});
    }
    let finalText='';
    if(textEntries.length&&textEntries.at(-1)?.message?.end_turn===true){
      finalText=textEntries.pop()?.content||'';
    }
    const messageTime=message=>{
      const value=Number(message?.create_time);
      return Number.isFinite(value)&&value>0?value:Number.POSITIVE_INFINITY;
    };
    const toolBlockTime=block=>{
      const lines=String(block||'').split('\\n');
      if(lines.length<3)return null;
      try{
        const payload=JSON.parse(lines.slice(1,-1).join('\\n'));
        const value=Number(payload?.created_at);
        return Number.isFinite(value)&&value>0?value:null;
      }catch{return null;}
    };
    const timeline=textEntries.map(entry=>({
      time:messageTime(entry.message),
      order:entry.index*2,
      content:entry.content
    }));
    const toolSources=[];
    for(const [index,message] of messages.entries()){
      const parsed=parsedByIndex[index];
      const recipient=String(message?.recipient||'');
      const path=parsed&&typeof parsed==='object'&&typeof parsed.path==='string'
        ?parsed.path:'';
      const wrapper=Boolean(parsed&&typeof parsed==='object'&&(
        parsed.type==='mcpToolCall'||parsed.appContext||parsed.arguments
      ));
      const invocation=recipient==='api_tool.call_tool'||Boolean(path);
      if((hasCompletedWrappers?wrapper:invocation))toolSources.push({index,message});
    }
    for(const [toolIndex,block] of tools.entries()){
      const source=toolSources[toolIndex];
      timeline.push({
        time:toolBlockTime(block)??(source?messageTime(source.message):Number.POSITIVE_INFINITY),
        order:source?source.index*2+1:messages.length*2+toolIndex,
        content:block
      });
    }
    timeline.sort((left,right)=>left.time-right.time||left.order-right.order);
    const parts=collapseStreamingTextParts(timeline.map(entry=>entry.content).filter(Boolean));
    if(finalText)parts.push(finalText);
    return collapseStreamingTextParts(parts).join('\\n\\n').trim();
  };
  const roleNodes=[...document.querySelectorAll(messageRoleSelector)];
  const agentRoot=node=>node?.closest?.(turnSelector)||node?.parentElement||null;
  const seededAssistantTurns=new Set();
  const entryNodes=roleNodes.filter(node=>{
    if(node.getAttribute('data-message-author-role')!=='assistant')return true;
    const turn=agentRoot(node);
    if(!turn)return true;
    if(seededAssistantTurns.has(turn))return false;
    seededAssistantTurns.add(turn);
    return true;
  });
  const entries=entryNodes.map(e=>{
    const role=e.getAttribute('data-message-author-role')||'';
    const rich=role==='assistant'
      ? [...e.querySelectorAll(markdownSelector)].map(markdownText).filter(Boolean).join('\\n\\n').trim()
      : '';
    return {
      node:e,
      id:e.getAttribute('data-message-id')||e.getAttribute('data-message-uuid')||'',
      role,
      content:role==='assistant'?rich:messageText(e)
    };
  }).filter(message=>message.role&&message.content&&!(
    message.role==='assistant'&&message.id.startsWith('request-placeholder-')
  ));
  const seenRoleKeys=new Set();
  for(let index=entries.length-1;index>=0;index-=1){
    const message=entries[index];
    const key=message.role+'|'+(message.id||normalise(message.content));
    if(seenRoleKeys.has(key))entries.splice(index,1);
    else seenRoleKeys.add(key);
  }
  const assistantNodes=roleNodes.filter(node=>node.getAttribute('data-message-author-role')==='assistant');
  const explicitUserTurns=new Set(roleNodes
    .filter(node=>node.getAttribute('data-message-author-role')==='user')
    .map(agentRoot)
    .filter(Boolean));
  const semanticAssistantTurns=[...document.querySelectorAll(turnSelector)]
    .filter(visible)
    .filter(turn=>!explicitUserTurns.has(turn))
    .filter(turn=>turn.querySelector(assistantSelector)||turn.querySelector(markdownSelector));
  const candidates=[...new Set([
    ...assistantNodes.map(agentRoot).filter(Boolean),
    ...semanticAssistantTurns
  ])].filter(visible);
  for(const [agentIndex,agent] of candidates.entries()){
    const reactOrdered=reactOrderedContent(agent);
    const reactHasVisibleText=reactHasVisibleAssistantText(agent);
    const markdownNodes=[...agent.querySelectorAll(markdownSelector)].filter(visible);
    const tools=toolBlocks(agent);
    const currentToolRows=[...agent.querySelectorAll('span[class~=\"group/tool-message\"]')];
    const legacyToolRows=[...new Set([
      ...agent.querySelectorAll(toolSelector)
    ])].filter(node=>!node.closest('span[class~=\"group/tool-message\"]')&&!node.querySelector(toolSelector));
    const toolRows=currentToolRows.length?currentToolRows:legacyToolRows;
    const markdown=markdownNodes.filter(node=>!toolRows.some(toolRow=>toolRow.contains(node)));
    const richText=markdown.map(markdownText).filter(Boolean);
    const richPlain=markdown.map(node=>(node.innerText||node.textContent||'').trim()).filter(Boolean);
    const orderedNodes=[
      ...markdown.map(node=>({node,kind:'markdown'})),
      ...toolRows.map(node=>({node,kind:'tool'}))
    ].sort((left,right)=>left.node===right.node?0:(
      left.node.compareDocumentPosition(right.node)&Node.DOCUMENT_POSITION_FOLLOWING?-1:1
    ));
    let orderedToolIndex=0;
    const orderedParts=orderedNodes.map(entry=>{
      if(entry.kind==='markdown')return markdownText(entry.node);
      const block=tools[orderedToolIndex]||'';
      orderedToolIndex+=1;
      return block;
    }).filter(Boolean);
    if(orderedToolIndex<tools.length)orderedParts.push(...tools.slice(orderedToolIndex));
    const rawVisible=(agent.innerText||agent.textContent||'').replace(networkErrorNoise,'').trim();
    const uiNoise=/^(?:copy|copy code|edit|good response|bad response|read aloud|regenerate|share|open tool call list|close tool call list|cot-v5-tool-icon-pile|connection interrupted\\.?(?:\\s*waiting for (?:the )?complete answer\\.?)?|waiting for (?:the )?complete answer\\.?|message delivery timed out\\.?\\s*please try again\\.?|a network error occurred\\.?(?:\\s*please check your connection and try again\\.?(?:\\s*if this issue persists please contact us through our help center at help\\.openai\\.com\\.?)?)?)$/i;
    const activityLines=[...new Set(rawVisible.split(/\\n+/).map(line=>line.trim()).filter(line=>(
      line
      && !uiNoise.test(line)
      && !richPlain.some(text=>text===line||text.includes(line)||line.includes(text))
      && !tools.some(block=>block.includes(line))
    )))].slice(0,200);
    const activity=!richText.length&&!tools.length&&activityLines.length
      ? '**Tool activity**\\n\\n'+activityLines.join('\\n')
      : '';
    const cleanVisible=rawVisible.split(/\\n+/).map(line=>line.trim())
      .filter(line=>line&&!uiNoise.test(line)&&!/^cot-v5-/i.test(line))
      .join('\\n').trim();
    const fallbackContent=(orderedParts.length||activity
      ? collapseStreamingTextParts([
          ...orderedParts,
          ...(activity?[activity]:[])
        ]).join('\\n\\n')
      : cleanVisible
    ).trim();
    const reactVisible=normalise(reactOrdered);
    const reactKeepsVisibleText=!richPlain.length||richPlain.every(text=>{
      const visibleText=normalise(text);
      return !visibleText||reactVisible.includes(visibleText);
    });
    const content=((reactOrdered&&reactHasVisibleText&&reactKeepsVisibleText)
      ?reactOrdered
      :fallbackContent
    ).trim();
    if(!content)continue;
    const nested=agent.querySelector(assistantSelector);
    const id=agent.getAttribute('data-message-id')
      ||agent.getAttribute('data-message-uuid')
      ||nested?.getAttribute('data-message-id')
      ||nested?.getAttribute('data-message-uuid')
      ||agent.closest('[data-message-id]')?.getAttribute('data-message-id')
      ||agent.closest('[data-message-uuid]')?.getAttribute('data-message-uuid')
      ||'';
    if(id.startsWith('request-placeholder-'))continue;
    let existing=id?entries.findIndex(message=>message.role==='assistant'&&message.id===id):-1;
    if(existing<0&&nested){
      existing=entries.findIndex(message=>message.node===nested);
    }
    if(existing<0){
      existing=entries.findIndex(message=>message.role==='assistant'&&message.content&&(
        content.startsWith(message.content)||message.content.startsWith(content)
      ));
    }
    if(existing>=0){
      if(content.length>=entries[existing].content.length)entries[existing].content=content;
      if(id&&!entries[existing].id)entries[existing].id=id;
      continue;
    }
    const precedingUser=roleNodes
      .filter(node=>node.getAttribute('data-message-author-role')==='user'
        &&Boolean(node.compareDocumentPosition(agent)&Node.DOCUMENT_POSITION_FOLLOWING))
      .at(-1);
    const turnSeed=precedingUser?.getAttribute('data-message-id')
      ||precedingUser?.getAttribute('data-message-uuid')
      ||normalise(messageText(precedingUser))
      ||('agent-'+agentIndex);
    entries.push({
      node:agent,
      id:id||('__prompta_live_assistant_'+hash(turnSeed)+'__'),
      role:'assistant',
      content
    });
  }
  entries.sort((left,right)=>{
    if(left.node===right.node)return 0;
    if(!left.node)return 1;
    if(!right.node)return -1;
    return left.node.compareDocumentPosition(right.node)&Node.DOCUMENT_POSITION_FOLLOWING?-1:1;
  });
  const pageReactRoot=document.querySelector('main')||document.body;
  const pageReactMessages=pageReactRoot?reactMessages(pageReactRoot):[];
  if(!entries.length&&pageReactMessages.length){
    for(const message of pageReactMessages){
      const role=String(message?.author?.role||message?.role||'');
      const recipient=String(message?.recipient||'');
      const content=message?.content||{};
      const contentType=String(content?.content_type||content?.type||'');
      if(!['user','assistant'].includes(role)||(recipient&&recipient!=='all')||(
        contentType!=='text'&&contentType!=='multimodal_text'
      ))continue;
      const parts=Array.isArray(content?.parts)
        ?content.parts.filter(part=>typeof part==='string'&&part.trim())
        :[];
      const raw=parts.length?parts.join('\\n'):String(content?.text||'');
      const contentText=(role==='assistant'?cleanAssistantText(raw):raw).trim();
      if(!contentText)continue;
      const id=String(message?.id||'');
      const previous=entries.at(-1);
      if(role==='assistant'&&previous?.role==='assistant'){
        previous.content=collapseStreamingTextParts([previous.content,contentText]).join('\\n\\n').trim();
        if(id)previous.id=id;
        continue;
      }
      entries.push({node:null,id,role,content:contentText});
    }
  }
  const messages=entries.map((message,index)=>({
    id:message.id,
    role:message.role,
    content:message.content,
    ordinal:index
  }));
  const latestAgent=candidates.at(-1)||null;
  const visibleAgentText=normalise(latestAgent?.innerText||latestAgent?.textContent||'');
  let latestTurnReactMessages=latestAgent?reactMessages(latestAgent):[];
  if(!latestTurnReactMessages.length&&pageReactMessages.length){
    latestTurnReactMessages=pageReactMessages;
  }
  const latestTurnUserIndex=latestTurnReactMessages.findLastIndex(message=>
    String(message?.author?.role||message?.role||'')==='user'
  );
  if(latestTurnUserIndex>=0){
    latestTurnReactMessages=latestTurnReactMessages.slice(latestTurnUserIndex+1);
  }
  let sourceEvents=latestTurnReactMessages.filter(message=>{
    const role=String(message?.author?.role||message?.role||'');
    const recipient=String(message?.recipient||'');
    if(role==='tool'||recipient==='api_tool.call_tool')return true;
    if(role!=='assistant'||(recipient&&recipient!=='all'))return false;
    if(message?.end_turn===true)return true;
    const content=message?.content||{};
    const contentType=String(content?.content_type||content?.type||'');
    const parts=Array.isArray(content?.parts)
      ?content.parts.filter(part=>typeof part==='string'&&part.trim())
      :[];
    const text=normalise(parts.length?parts.join(' '):String(content?.text||''));
    if(contentType==='text'||contentType==='multimodal_text')return Boolean(text);
    return false;
  }).map(sanitiseSourceEvent);
  const stop=[...document.querySelectorAll(stopSelector)].some(visible);
  const streamActive=[...document.querySelectorAll(streamingSelector)].some(visible);
  const latestAssistant=assistantNodes.at(-1)||latestAgent?.querySelector(assistantSelector)||null;
  const latestTurn=latestAssistant?agentRoot(latestAssistant):latestAgent;
  const visibleMessageId=latestAssistant?.getAttribute('data-message-id')
    ||latestAssistant?.getAttribute('data-message-uuid')
    ||latestTurn?.getAttribute('data-message-id')
    ||latestTurn?.getAttribute('data-message-uuid')
    ||'';
  const endStateMessages=latestTurn?reactMessages(latestTurn):latestTurnReactMessages;
  const endStates=(visibleMessageId
    ?endStateMessages.filter(message=>String(message?.id||'')===visibleMessageId)
    :endStateMessages.slice(-8)
  ).filter(message=>String(message?.author?.role||message?.role||'')==='assistant')
    .map(message=>message?.end_turn)
    .filter(value=>typeof value==='boolean');
  const turnEnded=endStates.includes(true)?true:(endStates.includes(false)?false:null);
  const sourceHasAssistantText=sourceEvents.some(event=>(
    event.role==='assistant'
    &&(event.recipient===''||event.recipient==='all')
    &&(event.content_type==='text'||event.content_type==='multimodal_text')
  ));
  if(latestAgent&&!sourceHasAssistantText){
    const toolRows=[...latestAgent.querySelectorAll('span[class~="group/tool-message"],'+toolSelector)];
    const visibleProse=[...latestAgent.querySelectorAll(markdownSelector)]
      .filter(visible)
      .filter(node=>!toolRows.some(toolRow=>toolRow.contains(node)))
      .map(markdownText)
      .filter(Boolean)
      .join('\\n\\n')
      .trim();
    if(visibleProse){
      const latestAssistantMessage=[...messages].reverse().find(message=>message.role==='assistant');
      const syntheticEndTurn=typeof turnEnded==='boolean'
        ?turnEnded
        :(!(stop||streamActive)?true:null);
      sourceEvents=[...sourceEvents,{
        id:(visibleMessageId||latestAssistantMessage?.id||'__prompta_visible_assistant__')+':dom-prose',
        parent_id:'',
        create_time:null,
        update_time:null,
        end_turn:syntheticEndTurn,
        status:'',
        role:'assistant',
        recipient:'all',
        content_type:'text',
        text:'',
        parts:[visibleProse],
        connector_tool_payload:'',
        reasoning_title:'',
        reasoning_titles:[],
        invoked_resource:null,
        connector_name:'',
        model_slug:'',
        request_id:'',
        attachments:[],
        citations:[],
        content_references:[]
      }];
    }
  }
  return {
    path:location.pathname,
    title:document.title||'',
    messages,
    source_events:sourceEvents,
    streaming:stop||streamActive||turnEnded===false
  };
})())"""

CONVERSATION_SNAPSHOT_SCRIPT = (
    CONVERSATION_SNAPSHOT_SCRIPT.replace(
        "__MESSAGE_ROLE_SELECTOR__", json.dumps(MESSAGE_ROLE_SELECTOR)
    )
    .replace("__ASSISTANT_SELECTOR__", json.dumps(ASSISTANT_MESSAGE_SELECTOR))
    .replace("__TURN_SELECTOR__", json.dumps(TURN_SELECTOR))
    .replace("__MARKDOWN_SELECTOR__", json.dumps(MARKDOWN_SELECTOR))
    .replace("__STOP_SELECTOR__", json.dumps(STOP_BUTTON_SELECTOR))
    .replace("__STREAMING_SELECTOR__", json.dumps(STREAMING_SELECTOR))
)


def parse_conversation_snapshot(raw: str) -> dict[str, Any]:
    return json.loads(raw or "{}")
