(async()=>{try{
              const sessionResponse=await fetch('/api/auth/session');
              const session=await sessionResponse.json();
              const token=session.accessToken||session.access_token||'';
              if(!sessionResponse.ok||!token)return JSON.stringify({ok:false,status:401});
              const response=await fetch(
                '/backend-api/conversation/'+encodeURIComponent(__CONVERSATION_ID__),
                {headers:{Authorization:'Bearer '+token}}
              );
              if(!response.ok)return JSON.stringify({ok:false,status:response.status});
              const payload=await response.json();
              const mapping=payload&&typeof payload.mapping==='object'?payload.mapping:{};
              const branch=[];
              const seen=new Set();
              let nodeId=String(payload.current_node||'');
              while(nodeId&&!seen.has(nodeId)){
                seen.add(nodeId);
                const node=mapping[nodeId];
                if(!node)break;
                if(node.message)branch.push({message:node.message,parent:String(node.parent||'')});
                nodeId=String(node.parent||'');
              }
              branch.reverse();
              let lastUser=-1;
              for(let index=0;index<branch.length;index+=1){
                const message=branch[index].message||{};
                if(String(message?.author?.role||message?.role||'')==='user')lastUser=index;
              }
              let finalEvent=null;
              for(let index=lastUser+1;index<branch.length;index+=1){
                const entry=branch[index];
                const message=entry.message||{};
                const role=String(message?.author?.role||message?.role||'');
                const recipient=String(message?.recipient||'');
                const content=message?.content||{};
                const contentType=String(content?.content_type||content?.type||'');
                if(
                  role!=='assistant'
                  ||(recipient&&recipient!=='all')
                  ||message?.end_turn!==true
                  ||(contentType!=='text'&&contentType!=='multimodal_text')
                )continue;
                const parts=Array.isArray(content?.parts)
                  ?content.parts.filter(part=>typeof part==='string'&&part.trim())
                  :[];
                const text=parts.length?parts.join('\n'):String(content?.text||'');
                if(!text.trim())continue;
                const metadata=message?.metadata||{};
                finalEvent={
                  id:String(message?.id||''),
                  parent_id:entry.parent,
                  create_time:Number.isFinite(Number(message?.create_time))
                    ?Number(message.create_time):null,
                  update_time:Number.isFinite(Number(message?.update_time))
                    ?Number(message.update_time):null,
                  end_turn:true,
                  status:String(message?.status||''),
                  role:'assistant',
                  recipient:recipient||'all',
                  content_type:contentType,
                  text:typeof content?.text==='string'?content.text:'',
                  parts,
                  reasoning_title:'',
                  reasoning_titles:[],
                  invoked_resource:null,
                  connector_name:'',
                  model_slug:String(metadata?.model_slug||metadata?.default_model_slug||''),
                  request_id:String(metadata?.request_id||metadata?.requestId||''),
                  attachments:[],
                  citations:Array.isArray(metadata?.citations)?metadata.citations:[],
                  content_references:Array.isArray(metadata?.content_references)
                    ?metadata.content_references:[]
                };
              }
              return JSON.stringify({
                ok:true,
                status:response.status,
                title:String(payload.title||''),
                final_event:finalEvent
              });
            }catch(error){
              return JSON.stringify({ok:false,status:0,error:String(error)});
            }})()
