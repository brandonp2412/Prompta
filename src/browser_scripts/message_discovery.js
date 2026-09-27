  const messageRoleSelector=__MESSAGE_ROLE_SELECTOR__;
  const assistantSelector=__ASSISTANT_SELECTOR__;
  const semanticTurnSelector=__SEMANTIC_TURN_SELECTOR__;
  const legacyTurnSelector=__LEGACY_TURN_SELECTOR__;
  const semanticAttribute=(node,namePattern)=>{
    if(!node?.attributes)return '';
    for(const attribute of node.attributes){
      if(namePattern.test(attribute.name))return String(attribute.value||'');
    }
    return '';
  };
  const semanticSearchRole=node=>{
    const key=semanticAttribute(node,/(?:^|-)search-unit-key$/i);
    return key.match(/:(user|assistant)$/)?.[1]||'';
  };
  const accessibleRole=value=>{
    const label=String(value||'').replace(/\s+/g,' ').trim();
    if(/^(?:you|user)(?:\s+(?:said|wrote|asked))?\s*:?$/i.test(label))return 'user';
    if(/^(?:chatgpt|assistant)(?:\s+(?:said|answered|responded))?\s*:?$/i.test(label))return 'assistant';
    return '';
  };
  const headingRole=node=>{
    if(!node?.querySelectorAll)return '';
    for(const heading of node.querySelectorAll('h1,h2,h3,h4,h5,h6')){
      const role=accessibleRole(heading.textContent);
      if(role)return role;
    }
    return '';
  };
  const directMessageRole=node=>String(
    node?.getAttribute?.('data-message-author-role')
    ||semanticAttribute(node,/(?:^|-)message-author-role$/i)
    ||semanticSearchRole(node)
    ||accessibleRole(node?.getAttribute?.('aria-label'))
    ||''
  );
  const messageRole=node=>directMessageRole(node)||headingRole(node);
  const searchMessageIds=node=>semanticAttribute(node,/(?:^|-)search-message-ids$/i)
    .split(/\s+/).filter(Boolean);
  const messageId=node=>String(
    node?.getAttribute?.('data-message-id')
    ||node?.getAttribute?.('data-message-uuid')
    ||semanticAttribute(node,/(?:^|-)(?:selection-)?message-(?:id|uuid)$/i)
    ||searchMessageIds(node).at(-1)
    ||''
  );
  const messageNodes=()=>{
    const primary=[...new Set([
      ...document.querySelectorAll(messageRoleSelector),
      ...document.querySelectorAll(semanticTurnSelector)
    ])].filter(node=>messageRole(node));
    const roles=new Set(primary.map(messageRole));
    const root=document.querySelector('main')||document.body||document.documentElement;
    const structural=roles.has('user')&&roles.has('assistant')?[]:
      [...root.querySelectorAll('*')].filter(node=>directMessageRole(node));
    const primarySelector=messageRoleSelector+','+semanticTurnSelector;
    const legacy=[...document.querySelectorAll(legacyTurnSelector)]
      .filter(node=>!node.querySelector(primarySelector))
      .filter(node=>messageRole(node));
    return [...new Set([...primary,...structural,...legacy])];
  };
  const authorNodes=role=>messageNodes()
    .filter(node=>!role||messageRole(node)===role);
  const authorNode=(root,role='')=>{
    if(!root)return null;
    if(messageRole(root)&&(!role||messageRole(root)===role))return root;
    return [...new Set([
      ...root.querySelectorAll(messageRoleSelector),
      ...root.querySelectorAll(semanticTurnSelector)
    ])].find(node=>messageRole(node)&&(!role||messageRole(node)===role))||null;
  };
  const semanticTurnRoot=node=>node?.closest?.(semanticTurnSelector)||null;
  const structuralTurnRoot=node=>{
    if(!node)return null;
    let candidate=null;
    for(let parent=node.parentElement;parent&&parent!==document.body;parent=parent.parentElement){
      if(parent.tagName==='MAIN'||parent.getAttribute?.('role')==='main')break;
      const authors=[...parent.querySelectorAll(messageRoleSelector)];
      if(authors.length!==1||authors[0]!==node)break;
      candidate=parent;
    }
    return candidate;
  };
  const legacyTurnRoot=node=>node?.closest?.(legacyTurnSelector)||null;
  const turnRoot=node=>semanticTurnRoot(node)
    ||structuralTurnRoot(node)
    ||legacyTurnRoot(node)
    ||node
    ||null;
  const turnMessageId=(turn,role='')=>messageId(turn)
    ||messageId(authorNode(turn,role))
    ||messageId(turn?.querySelector?.('[data-message-id],[data-message-uuid]'))
    ||'';
