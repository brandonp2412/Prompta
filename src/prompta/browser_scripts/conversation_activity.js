JSON.stringify((()=>{
          const assistantSelector=__ASSISTANT_SELECTOR__;
          const turnSelector=__TURN_SELECTOR__;
          const stopSelector=__STOP_SELECTOR__;
          const streamingSelector=__STREAMING_SELECTOR__;
          const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';};
          const stop=[...document.querySelectorAll(stopSelector)].some(visible);
          const streamActive=[...document.querySelectorAll(streamingSelector)].some(visible);
          const assistants=[...document.querySelectorAll(assistantSelector)];
          const assistant=assistants.at(-1);
          const candidateTurns=[...document.querySelectorAll(turnSelector)].filter(visible);
          const turn=assistant?.closest(turnSelector)||assistant?.parentElement||candidateTurns.at(-1)||null;
          const visibleMessageId=assistant?.getAttribute('data-message-id')
            ||assistant?.getAttribute('data-message-uuid')
            ||turn?.getAttribute('data-message-id')
            ||turn?.getAttribute('data-message-uuid')
            ||turn?.querySelector('[data-message-id]')?.getAttribute('data-message-id')
            ||turn?.querySelector('[data-message-uuid]')?.getAttribute('data-message-uuid')
            ||'';
          const reactTurnEnd=()=>{
            const root=turn||document.querySelector('main')||document.body;
            if(!root)return null;
            const found=[],seenObjects=new WeakSet(),seenArrays=new WeakSet();
            const add=messages=>{
              if(!Array.isArray(messages)||seenArrays.has(messages))return;
              seenArrays.add(messages);
              found.push(...messages.filter(message=>message&&typeof message==='object'&&message.content&&message.author));
            };
            const walk=(value,depth)=>{
              if(!value||depth>7||(typeof value!=='object'&&typeof value!=='function'))return;
              if(seenObjects.has(value))return;
              seenObjects.add(value);
              if(Array.isArray(value)){if(depth<=5)add(value);return;}
              let keys=[];
              try{keys=Object.keys(value);}catch{return;}
              for(const key of keys.slice(0,260)){
                if(['ref','_owner','return','child','sibling','stateNode','alternate'].includes(key))continue;
                let next;
                try{next=value[key];}catch{continue;}
                if(key==='messages')add(next);
                if(next&&depth<7&&(typeof next==='object'||typeof next==='function'))walk(next,depth+1);
              }
            };
            for(const node of [root,...root.querySelectorAll('*')]){
              let keys=[];
              try{keys=Object.getOwnPropertyNames(node).filter(name=>name.startsWith('__reactProps$')||name.startsWith('__reactFiber$')||name.startsWith('__reactContainer$'));}catch{}
              for(const key of keys)walk(node[key],0);
            }
            const assistantMessages=found.filter(message=>String(message?.author?.role||message?.role||'')==='assistant');
            const target=visibleMessageId
              ?assistantMessages.filter(message=>String(message?.id||'')===visibleMessageId)
              :assistantMessages.slice(-8);
            const states=target.map(message=>message?.end_turn).filter(value=>typeof value==='boolean');
            if(states.includes(true))return true;
            if(states.includes(false))return false;
            return null;
          };
          const turnEnded=reactTurnEnd();
          const turnText=(turn?.innerText||turn?.textContent||'').trim();
          const transientText=/(?:Connection interrupted|Waiting for the complete answer|A network error occurred\.?\s*Please check your connection and try again\.?\s*If this issue persists please contact us through our help center at help\.openai\.com\.?)/i.test(turnText);
          const deliveryFailed=/Message delivery timed out\.?\s*Please try again/i.test(turnText);
          const finalAction=Boolean(turn&&[...turn.querySelectorAll('button')].some(button=>{
            const testId=(button.getAttribute('data-testid')||'').trim();
            const label=(button.getAttribute('aria-label')||button.getAttribute('title')||button.textContent||'').trim();
            return testId==='copy-turn-action-button'||/^Copy(?: response)?$/i.test(label);
          }));
          const streaming=stop||streamActive||turnEnded===false;
          const complete=!streaming&&(turnEnded===true||(turnEnded===null&&finalAction));
          const transient=transientText&&!complete;
          const failed=deliveryFailed&&!complete&&!streaming;
          return {streaming,complete,transient,failed,turn_ended:turnEnded};
        })())
