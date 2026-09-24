  const reactFallback=(()=>{
    const provenance='react-private-properties';
    const prefixes=['__reactProps$','__reactFiber$','__reactContainer$'];
    const allowedReasons=new Set([
      'transcript-gap',
      'assistant-enrichment',
      'tool-enrichment',
      'source-events',
      'end-state',
      'activity-end-state',
      'chromium-tool-enrichment'
    ]);
    const inspect=(root,{allow=false,reason='',maxDepth=7,maxKeys=240,maxNodes=1200,maxObjects=12000,maxMillis=2000}={})=>{
      const result={
        allowed:Boolean(allow)&&allowedReasons.has(reason),
        used:false,
        available:false,
        provenance,
        reason:String(reason||''),
        property_names:[],
        messages:[],
        truncated:false,
        scanned_nodes:0,
        scanned_objects:0,
        error:''
      };
      if(!result.allowed)return result;
      if(!root){result.used=true;return result;}
      result.used=true;
      try{
        const found=[],seenObjects=new WeakSet(),seenArrays=new WeakSet(),propertyNames=new Set();
        const deadline=performance.now()+Math.max(1,Number(maxMillis)||1);
        const nodeLimit=Math.max(1,Number(maxNodes)||1);
        const objectLimit=Math.max(1,Number(maxObjects)||1);
        const budgetExhausted=()=>performance.now()>=deadline
          ||result.scanned_nodes>=nodeLimit
          ||result.scanned_objects>=objectLimit;
        const add=messages=>{
          if(!Array.isArray(messages)||seenArrays.has(messages))return;
          seenArrays.add(messages);
          if(messages.some(message=>message&&typeof message==='object'&&message.content&&message.author)){
            found.push(...messages);
          }
        };
        const walk=(value,depth)=>{
          if(!value||depth>maxDepth||(typeof value!=='object'&&typeof value!=='function'))return;
          if(seenObjects.has(value))return;
          if(budgetExhausted()){result.truncated=true;return;}
          seenObjects.add(value);
          result.scanned_objects+=1;
          if(Array.isArray(value)){if(depth<=Math.max(0,maxDepth-2))add(value);return;}
          let keys=[];
          try{keys=Object.keys(value);}catch{return;}
          for(const key of keys.slice(0,maxKeys)){
            if(performance.now()>=deadline){result.truncated=true;break;}
            if(['ref','_owner','return','child','sibling','stateNode','alternate'].includes(key))continue;
            let next;
            try{next=value[key];}catch{continue;}
            if(key==='messages')add(next);
            if(next&&depth<maxDepth&&(typeof next==='object'||typeof next==='function')){
              walk(next,depth+1);
            }
          }
        };
        for(const node of [root,...root.querySelectorAll('*')]){
          if(budgetExhausted()){result.truncated=true;break;}
          result.scanned_nodes+=1;
          let keys=[];
          try{
            keys=Object.getOwnPropertyNames(node).filter(name=>prefixes.some(prefix=>name.startsWith(prefix)));
          }catch{continue;}
          for(const key of keys){
            propertyNames.add(key);
            let value;
            try{value=node[key];}catch{continue;}
            walk(value,0);
          }
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
        const ready=indegree.map((degree,index)=>degree===0?index:null).filter(index=>index!==null);
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
          const orderedSet=new Set(ordered);
          ordered.push(...unique.map((_,index)=>index).filter(index=>!orderedSet.has(index)).sort(priority));
        }
        result.property_names=[...propertyNames];
        result.messages=ordered.map(index=>unique[index]);
        result.available=Boolean(result.property_names.length);
        if(result.truncated&&!result.error){
          result.error='React fallback introspection budget exhausted';
        }
      }catch(error){
        result.error=String(error?.message||error||'React fallback introspection failed');
      }
      return result;
    };
    return {inspect};
  })();
