  const messageRoleSelector=__MESSAGE_ROLE_SELECTOR__;
  const assistantSelector=__ASSISTANT_SELECTOR__;
  const semanticTurnSelector=__SEMANTIC_TURN_SELECTOR__;
  const legacyTurnSelector=__LEGACY_TURN_SELECTOR__;
  const semanticSearchRole=node=>{
    const key=String(
      node?.getAttribute?.('data-chatgpt-search-unit-key')
      ||node?.getAttribute?.('data-content-search-unit-key')
      ||''
    );
    return key.match(/:(user|assistant)$/)?.[1]||'';
  };
  const messageRole=node=>String(
    node?.getAttribute?.('data-message-author-role')
    ||semanticSearchRole(node)
    ||''
  );
  const searchMessageIds=node=>String(
    node?.getAttribute?.('data-chatgpt-search-message-ids')||''
  ).split(/\s+/).filter(Boolean);
  const messageId=node=>String(
    node?.getAttribute?.('data-message-id')
    ||node?.getAttribute?.('data-message-uuid')
    ||node?.getAttribute?.('data-chatgpt-selection-message-id')
    ||searchMessageIds(node).at(-1)
    ||''
  );
  const messageNodes=()=>[...new Set([
    ...document.querySelectorAll(messageRoleSelector),
    ...document.querySelectorAll(semanticTurnSelector)
  ])].filter(node=>messageRole(node));
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
