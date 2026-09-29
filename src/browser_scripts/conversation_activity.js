JSON.stringify((()=>{
/*__TRANSCRIPT_BROWSER_ENGINE__*/
          const stopSelector=__STOP_SELECTOR__;
          const streamingSelector=__STREAMING_SELECTOR__;
          const rendered=e=>promptaTranscriptEngine.isRenderedNode(e);
          const visible=e=>{
            if(!rendered(e))return false;
            const s=getComputedStyle(e);
            const r=e.getBoundingClientRect();
            if((r.width>0||r.height>1)&&r.height>0)return true;
            if(s.display!=='contents')return false;
            return deepQueryAll(e,'*').some(node=>{
              if(!rendered(node))return false;
              const box=node.getBoundingClientRect();
              return (box.width>0||box.height>1)&&box.height>0;
            });
          };
          const renderedTextContent=node=>{
            if(!node)return '';
            if(node.nodeType===Node.TEXT_NODE)return node.nodeValue||'';
            if(node.nodeType===Node.ELEMENT_NODE&&!rendered(node))return '';
            return composedChildNodes(node).map(renderedTextContent).join('');
          };
          const semanticStop=promptaTranscriptEngine.actionControls(document)
            .some(node=>visible(node)&&promptaTranscriptEngine.isStopControl(node));
          const stop=deepQueryAll(document,stopSelector).some(visible)||semanticStop;
          const assistantNodes=authorNodes('assistant');
          const assistant=[...assistantNodes].reverse()
            .find(node=>visible(turnRoot(node)||node))
            ||assistantNodes.at(-1)
            ||null;
          const transcript=transcriptRoot();
          const semanticTurns=deepQueryAll(transcript,semanticTurnSelector).filter(visible);
          const legacyTurns=deepQueryAll(transcript,legacyTurnSelector).filter(visible);
          const turn=turnRoot(assistant)||semanticTurns.at(-1)||legacyTurns.at(-1)||null;
          const streamRoot=turn||assistant;
          const currentStreamNodes=()=>{
            if(!streamRoot)return [transcript,...deepQueryAll(transcript,'*')];
            const nodes=[streamRoot,...deepQueryAll(streamRoot,'*')];
            for(let current=composedParent(streamRoot);current;current=composedParent(current)){
              nodes.push(current);
              if(current===transcript||current===document.body||current===document.documentElement)break;
            }
            return [...new Set(nodes)];
          };
          const streamNodes=currentStreamNodes();
          const semanticStreamActive=streamNodes.some(node=>{
            if(!rendered(node))return false;
            const state=semanticAttribute(
              node,
              /(?:^|-)(?:is-)?streaming$/i,
              [['streaming']]
            ).toLowerCase();
            return ['true','active','1','yes'].includes(state)
              ||(node.getAttribute?.('aria-busy')||'').toLowerCase()==='true';
          });
          const streamActive=streamNodes.some(node=>
            node?.matches?.(streamingSelector)&&visible(node)
          )||semanticStreamActive;
          const visibleMessageId=messageId(assistant)||turnMessageId(turn,'assistant');
          let activityReactFallback=null;
          const reactTurnEnd=()=>{
            const root=turn||transcript;
            if(!root)return null;
            activityReactFallback=promptaTranscriptEngine.inspectReact(
              root,
              'activity-end-state',
              {maxDepth:7,maxKeys:260}
            );
            const found=activityReactFallback.messages;
            const assistantMessages=found.filter(message=>String(message?.author?.role||message?.role||'')==='assistant');
            const target=visibleMessageId
              ?assistantMessages.filter(message=>String(message?.id||'')===visibleMessageId)
              :assistantMessages.slice(-8);
            const states=target.map(message=>message?.end_turn).filter(value=>typeof value==='boolean');
            if(states.includes(true))return true;
            if(states.includes(false))return false;
            return null;
          };
          const turnText=renderedTextContent(turn).trim();
          const transientText=/(?:Connection interrupted|Waiting for the complete answer|A network error occurred\.?\s*Please check your connection and try again\.?\s*If this issue persists please contact us through our help center at help\.openai\.com\.?)/i.test(turnText);
          const deliveryFailed=/Message delivery timed out\.?\s*Please try again/i.test(turnText);
          const finalAction=Boolean(turn&&promptaTranscriptEngine.actionControls(turn)
            .some(control=>visible(control)&&promptaTranscriptEngine.isTurnActionControl(control)));
          const needsReactEndState=Boolean(turn&&!stop&&!streamActive&&!finalAction);
          const turnEnded=needsReactEndState?reactTurnEnd():null;
          const streaming=stop||streamActive||turnEnded===false;
          const complete=!streaming&&(turnEnded===true||(turnEnded===null&&finalAction));
          const transient=transientText&&!complete;
          const failed=deliveryFailed&&!complete&&!streaming;
          return {
            streaming,complete,transient,failed,turn_ended:turnEnded,
            react_fallback:activityReactFallback
          };
        })())
