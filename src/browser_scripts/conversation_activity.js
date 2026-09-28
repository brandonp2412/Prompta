JSON.stringify((()=>{
/*__TRANSCRIPT_BROWSER_ENGINE__*/
          const stopSelector=__STOP_SELECTOR__;
          const streamingSelector=__STREAMING_SELECTOR__;
          const visible=e=>{
            if(!e)return false;
            const s=getComputedStyle(e);
            if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0')return false;
            const r=e.getBoundingClientRect();
            if((r.width>0||r.height>1)&&r.height>0)return true;
            if(s.display!=='contents')return false;
            return [...e.querySelectorAll('*')].some(node=>{
              const style=getComputedStyle(node);
              if(style.display==='none'||style.visibility==='hidden'||style.opacity==='0')return false;
              const box=node.getBoundingClientRect();
              return (box.width>0||box.height>1)&&box.height>0;
            });
          };
          const semanticStop=promptaTranscriptEngine.interactiveControls(document)
            .some(node=>visible(node)&&promptaTranscriptEngine.isStopControl(node));
          const stop=[...document.querySelectorAll(stopSelector)].some(visible)||semanticStop;
          const assistant=authorNodes('assistant').at(-1)||null;
          const transcript=transcriptRoot();
          const semanticTurns=[...transcript.querySelectorAll(semanticTurnSelector)].filter(visible);
          const legacyTurns=[...transcript.querySelectorAll(legacyTurnSelector)].filter(visible);
          const turn=turnRoot(assistant)||semanticTurns.at(-1)||legacyTurns.at(-1)||null;
          const streamRoot=turn||assistant;
          const semanticStreamActive=Boolean(streamRoot&&[streamRoot,...streamRoot.querySelectorAll('*')].some(node=>{
            const state=semanticAttribute(
              node,
              /(?:^|-)(?:is-)?streaming$/i,
              [['streaming']]
            ).toLowerCase();
            return ['true','active','1','yes'].includes(state)
              ||(node.getAttribute?.('aria-busy')||'').toLowerCase()==='true';
          }));
          const streamActive=[...transcript.querySelectorAll(streamingSelector)].some(visible)||semanticStreamActive;
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
          const turnText=(turn?.innerText||turn?.textContent||'').trim();
          const transientText=/(?:Connection interrupted|Waiting for the complete answer|A network error occurred\.?\s*Please check your connection and try again\.?\s*If this issue persists please contact us through our help center at help\.openai\.com\.?)/i.test(turnText);
          const deliveryFailed=/Message delivery timed out\.?\s*Please try again/i.test(turnText);
          const finalAction=Boolean(turn&&promptaTranscriptEngine.interactiveControls(turn)
            .some(control=>promptaTranscriptEngine.isTurnActionControl(control)));
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
