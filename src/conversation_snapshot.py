from __future__ import annotations

import json
from typing import Any

from .chatgpt_dom import (
    LEGACY_RICH_TEXT_SELECTOR,
    PROSE_BLOCK_SELECTOR,
    STOP_BUTTON_SELECTOR,
    STREAMING_SELECTOR,
)
from .transcript_browser_engine import TRANSCRIPT_BROWSER_ENGINE_SCRIPT

CONVERSATION_SNAPSHOT_SCRIPT = """JSON.stringify((()=>{
  const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
  const normalise=value=>(value||'').replace(/\\s+/g,' ').trim();
  const hash=value=>{let h=2166136261;for(const ch of value){h^=ch.charCodeAt(0);h=Math.imul(h,16777619);}return (h>>>0).toString(36);};
__TRANSCRIPT_BROWSER_ENGINE__
  const proseBlockSelector=__PROSE_BLOCK_SELECTOR__;
  const legacyRichTextSelector=__LEGACY_RICH_TEXT_SELECTOR__;
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
  const toolDataSelector='[data-tool-call-id],[data-tool-name]';
  const toolTriggerSelector='button[aria-label="Open tool call list"],button[aria-label="Close tool call list"],[role="button"][aria-label="Open tool call list"],[role="button"][aria-label="Close tool call list"]';
  const legacyToolRowSelector='span[class~="group/tool-message"]';
  const toolNoise=/^(?:Open tool call list|Close tool call list|Tool|Tool call|Expand|Collapse|cot-v5-[\\w-]+)$/i;
  const cleanToolName=value=>{const text=(value||'').replace(/\\s+/g,' ').trim();return text&&!toolNoise.test(text)?text:'';};
  const toolRows=agent=>{
    if(!agent)return [];
    const dataRows=[...agent.querySelectorAll(toolDataSelector)].filter(node=>
      !node.parentElement?.closest(toolDataSelector)
    );
    const triggerRows=[...agent.querySelectorAll(toolTriggerSelector)].map(marker=>{
      const dataRow=marker.closest(toolDataSelector);
      if(dataRow&&agent.contains(dataRow))return dataRow;
      const control=marker.closest('button,[role="button"]')||marker;
      return control.parentElement&&agent.contains(control.parentElement)?control.parentElement:control;
    });
    const semantic=[...new Set([...dataRows,...triggerRows])]
      .filter(node=>node&&visible(node))
      .filter((node,index,rows)=>!rows.some((other,otherIndex)=>
        otherIndex!==index&&other.contains(node)
      ));
    const legacy=[...agent.querySelectorAll(legacyToolRowSelector)]
      .filter(node=>visible(node))
      .filter(node=>!semantic.some(row=>row===node||row.contains(node)||node.contains(row)));
    return [...semantic,...legacy].sort((left,right)=>left===right?0:(
      left.compareDocumentPosition(right)&Node.DOCUMENT_POSITION_FOLLOWING?-1:1
    ));
  };
  const proseRows=(agent,rows=toolRows(agent))=>{
    if(!agent)return [];
    const scope=authorNode(agent,'assistant')||agent;
    const isInsideTool=node=>rows.some(row=>row===node||row.contains(node));
    const semantic=[...scope.querySelectorAll(proseBlockSelector)]
      .filter(visible)
      .filter(node=>!isInsideTool(node))
      .filter((node,index,nodes)=>!nodes.some((other,otherIndex)=>
        otherIndex!==index&&other.contains(node)
      ));
    if(semantic.length)return semantic;
    const legacy=[...scope.querySelectorAll(legacyRichTextSelector)]
      .filter(visible)
      .filter(node=>!isInsideTool(node));
    if(legacy.length)return legacy;
    const structural=[...scope.children]
      .filter(visible)
      .filter(node=>!rows.some(row=>row===node||row.contains(node)||node.contains(row)))
      .filter(node=>normalise(messageText(node)));
    if(structural.length)return structural;
    return !rows.length&&normalise(messageText(scope))?[scope]:[];
  };
  const reactMessages=promptaTranscriptEngine.reactMessages;
  const reactHasVisibleAssistantText=promptaTranscriptEngine.hasVisibleAssistantText;
  const sanitiseSourceEvent=promptaTranscriptEngine.sanitiseSourceEvent;
  const reactToolBlocks=messages=>{
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
  const toolBlocks=(agent,fallbackMessages=[])=>{
    const domBlocks=toolRows(agent).map(node=>{
      const marker=node.matches(toolDataSelector+','+toolTriggerSelector)
        ?node
        :node.querySelector(toolDataSelector+','+toolTriggerSelector);
      const lines=(node.innerText||node.textContent||'').split(/\\n+/)
        .map(line=>line.trim())
        .filter(Boolean);
      const name=[
        node.getAttribute('data-tool-name'),
        marker?.getAttribute?.('data-tool-name'),
        node.getAttribute('title'),
        marker?.getAttribute?.('title'),
        ...lines
      ].map(cleanToolName).find(line=>line&&!/^Called tool$/i.test(line))||'';
      const detail=lines
        .map(cleanToolName)
        .filter(line=>line&&normalise(line)!==normalise(name))
        .join('\\n').trim().slice(0,16000);
      const body=detail||(!name?'Called tool':'');
      if(!body&&!name)return '';
      return '```tool:'+(name||'tool')+'\\n'+body+'\\n```';
    }).filter(Boolean);
    return domBlocks.length?domBlocks:reactToolBlocks(fallbackMessages);
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
  const reactOrderedContent=messages=>{
    if(!messages.length)return '';
    const tools=reactToolBlocks(messages);
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
  const roleNodes=authorNodes();
  const userNodes=authorNodes('user');
  const assistantNodes=authorNodes('assistant');
  const seededAssistantTurns=new Set();
  const entryNodes=roleNodes.filter(node=>{
    if(messageRole(node)!=='assistant')return true;
    const turn=turnRoot(node);
    if(!turn)return true;
    if(seededAssistantTurns.has(turn))return false;
    seededAssistantTurns.add(turn);
    return true;
  });
  const entries=entryNodes.map(e=>{
    const role=messageRole(e);
    const rich=role==='assistant'
      ? proseRows(e).map(markdownText).filter(Boolean).join('\\n\\n').trim()
      : '';
    return {
      node:e,
      id:messageId(e),
      role,
      content:role==='assistant'?rich:messageText(e)
    };
  }).filter(message=>message.role&&message.content&&!(
    message.role==='assistant'&&message.id.startsWith('request-placeholder-')
  ));
  const dedupedEntries=[];
  const seenRoleKeys=new Map();
  for(const message of entries){
    const key=message.role+'|'+(message.id||normalise(message.content));
    const existingIndex=seenRoleKeys.get(key);
    if(existingIndex===undefined){
      seenRoleKeys.set(key,dedupedEntries.length);
      dedupedEntries.push(message);
      continue;
    }
    const existing=dedupedEntries[existingIndex];
    const existingVisible=visible(turnRoot(existing.node)||existing.node);
    const messageVisible=visible(turnRoot(message.node)||message.node);
    if(messageVisible||!existingVisible){
      dedupedEntries[existingIndex]=message;
    }
  }
  entries.splice(0,entries.length,...dedupedEntries);
  const explicitUserTurns=new Set(userNodes.map(turnRoot).filter(Boolean));
  const semanticAssistantTurns=[...new Set([
    ...assistantNodes.map(turnRoot).filter(Boolean),
    ...document.querySelectorAll(semanticTurnSelector)
  ])]
    .filter(visible)
    .filter(turn=>!explicitUserTurns.has(turn))
    .filter(turn=>authorNode(turn,'assistant')||proseRows(turn).length);
  const semanticAssistantSet=new Set(semanticAssistantTurns);
  // Legacy fallback: class/tag turn wrappers are consulted only for layouts
  // that do not expose an author node or stable conversation-turn marker.
  const legacyAssistantTurns=[...document.querySelectorAll(legacyTurnSelector)]
    .filter(visible)
    .filter(turn=>!semanticAssistantSet.has(turn))
    .filter(turn=>!authorNode(turn,'user'))
    .filter(turn=>authorNode(turn,'assistant')||proseRows(turn).length);
  const candidates=[...new Set([
    ...semanticAssistantTurns,
    ...legacyAssistantTurns
  ])];
  for(const [agentIndex,agent] of candidates.entries()){
    const rows=toolRows(agent);
    const prose=proseRows(agent,rows);
    const richText=prose.map(markdownText).filter(Boolean);
    const richPlain=prose.map(node=>(node.innerText||node.textContent||'').trim()).filter(Boolean);
    const explicitAssistant=authorNode(agent,'assistant');
    const domTools=toolBlocks(agent);
    const rawVisible=(agent.innerText||agent.textContent||'').replace(networkErrorNoise,'').trim();
    const uiNoise=/^(?:copy|copy code|edit|good response|bad response|read aloud|regenerate|share|open tool call list|close tool call list|cot-v5-tool-icon-pile|connection interrupted\\.?(?:\\s*waiting for (?:the )?complete answer\\.?)?|waiting for (?:the )?complete answer\\.?|message delivery timed out\\.?\\s*please try again\\.?|a network error occurred\\.?(?:\\s*please check your connection and try again\\.?(?:\\s*if this issue persists please contact us through our help center at help\\.openai\\.com\\.?)?)?)$/i;
    const activityLines=[...new Set(rawVisible.split(/\\n+/).map(line=>line.trim()).filter(line=>(
      line
      && !uiNoise.test(line)
      && !richPlain.some(text=>text===line||text.includes(line)||line.includes(text))
      && !domTools.some(block=>block.includes(line))
    )))].slice(0,200);
    const needsReactFallback=Boolean(
      !explicitAssistant
      && !richText.length
      && !domTools.length
      && activityLines.length
    );
    const fallbackMessages=needsReactFallback
      ?reactMessages(agent,'assistant-enrichment')
      :[];
    const tools=domTools.length?domTools:toolBlocks(agent,fallbackMessages);
    const orderedNodes=[
      ...prose.map(node=>({node,kind:'prose'})),
      ...rows.map(node=>({node,kind:'tool'}))
    ].sort((left,right)=>left.node===right.node?0:(
      left.node.compareDocumentPosition(right.node)&Node.DOCUMENT_POSITION_FOLLOWING?-1:1
    ));
    let orderedToolIndex=0;
    const orderedParts=orderedNodes.map(entry=>{
      if(entry.kind==='prose')return markdownText(entry.node);
      const block=tools[orderedToolIndex]||'';
      orderedToolIndex+=1;
      return block;
    }).filter(Boolean);
    if(orderedToolIndex<tools.length)orderedParts.push(...tools.slice(orderedToolIndex));
    const activity=!explicitAssistant&&!richText.length&&!tools.length&&activityLines.length
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
    const reactOrdered=reactOrderedContent(fallbackMessages);
    const reactHasVisibleText=reactHasVisibleAssistantText(agent,fallbackMessages);
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
    const nested=authorNode(agent,'assistant');
    const id=turnMessageId(agent,'assistant');
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
    const precedingUser=userNodes
      .filter(node=>Boolean(node.compareDocumentPosition(agent)&Node.DOCUMENT_POSITION_FOLLOWING))
      .at(-1);
    const turnSeed=messageId(precedingUser)
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
  const pageReactMessages=(!entries.length&&pageReactRoot)
    ?reactMessages(pageReactRoot,'transcript-gap')
    :[];
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
  const latestHasToolDom=Boolean(latestAgent&&toolRows(latestAgent).length);
  let latestTurnReactMessages=(latestAgent&&latestHasToolDom)
    ?reactMessages(latestAgent,'source-events')
    :[];
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
  const latestAssistant=assistantNodes.at(-1)||authorNode(latestAgent,'assistant')||null;
  const latestTurn=latestAssistant?turnRoot(latestAssistant):latestAgent;
  const visibleMessageId=messageId(latestAssistant)||turnMessageId(latestTurn,'assistant');
  const endStateMessages=latestTurnReactMessages.length
    ?latestTurnReactMessages
    :((latestTurn&&latestHasToolDom&&!stop&&!streamActive)
      ?reactMessages(latestTurn,'end-state')
      :[]);
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
    const rows=toolRows(latestAgent);
    const visibleProse=proseRows(latestAgent,rows)
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
    streaming:stop||streamActive||turnEnded===false,
    react_fallback:promptaTranscriptEngine.reactFallbackSummary()
  };
})())"""

CONVERSATION_SNAPSHOT_SCRIPT = (
    CONVERSATION_SNAPSHOT_SCRIPT.replace(
        "__TRANSCRIPT_BROWSER_ENGINE__", TRANSCRIPT_BROWSER_ENGINE_SCRIPT
    )
    .replace("__PROSE_BLOCK_SELECTOR__", json.dumps(PROSE_BLOCK_SELECTOR))
    .replace("__LEGACY_RICH_TEXT_SELECTOR__", json.dumps(LEGACY_RICH_TEXT_SELECTOR))
    .replace("__STOP_SELECTOR__", json.dumps(STOP_BUTTON_SELECTOR))
    .replace("__STREAMING_SELECTOR__", json.dumps(STREAMING_SELECTOR))
)


def parse_conversation_snapshot(raw: str) -> dict[str, Any]:
    return json.loads(raw or "{}")
