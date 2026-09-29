JSON.stringify((()=>{
/*__MESSAGE_DISCOVERY__*/
  const rendered=node=>{
    for(let current=node;current&&current.nodeType===Node.ELEMENT_NODE;current=composedParent(current)){
      if(current.hidden||(current.getAttribute?.('aria-hidden')||'').toLowerCase()==='true')return false;
      const style=getComputedStyle(current);
      if(style.display==='none'||style.visibility==='hidden'||style.opacity==='0')return false;
    }
    return true;
  };
  const users=authorNodes('user');
  const user=[...users].reverse().find(rendered)||users.at(-1)||null;
  if(!user)return {id:'',text:''};

  const raw=semanticMessageText(user);
  const suffix=['Show moreShow less','Show lessShow more'].find(value=>raw.endsWith(value));
  const text=(suffix?raw.slice(0,-suffix.length):raw).trim();
  const turn=turnRoot(user);
  return {
    id:messageId(user)||turnMessageId(turn,'user'),
    text
  };
})())
