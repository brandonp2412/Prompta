JSON.stringify((()=>{
/*__TRANSCRIPT_BROWSER_ENGINE__*/
          const stopSelector=__STOP_SELECTOR__;
          const streamingSelector=__STREAMING_SELECTOR__;
          const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
          const stop=[...document.querySelectorAll(stopSelector)].some(visible);
          const streamActive=[...document.querySelectorAll(streamingSelector)].some(visible);
          const assistant=authorNodes('assistant').at(-1)||null;
          const semanticTurns=[...document.querySelectorAll(semanticTurnSelector)].filter(visible);
          const legacyTurns=[...document.querySelectorAll(legacyTurnSelector)].filter(visible);
          const turn=turnRoot(assistant)||semanticTurns.at(-1)||legacyTurns.at(-1)||null;
          const visibleMessageId=messageId(assistant)||turnMessageId(turn,'assistant');
          let activityReactFallback=null;
          const reactTurnEnd=()=>{
            const root=turn||document.querySelector('main')||document.body;
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
          const finalAction=Boolean(turn&&[...turn.querySelectorAll('button')].some(button=>{
            const testId=(button.getAttribute('data-testid')||'').trim();
            const label=(button.getAttribute('aria-label')||button.getAttribute('title')||button.textContent||'').trim();
            return testId==='copy-turn-action-button'||/^Copy(?: response)?$/i.test(label);
          }));
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
