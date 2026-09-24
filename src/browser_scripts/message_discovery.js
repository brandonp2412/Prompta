  const messageRoleSelector=__MESSAGE_ROLE_SELECTOR__;
  const assistantSelector=__ASSISTANT_SELECTOR__;
  const semanticTurnSelector=__SEMANTIC_TURN_SELECTOR__;
  const legacyTurnSelector=__LEGACY_TURN_SELECTOR__;
  const messageRole=node=>String(node?.getAttribute?.('data-message-author-role')||'');
  const messageId=node=>String(
    node?.getAttribute?.('data-message-id')
    ||node?.getAttribute?.('data-message-uuid')
    ||''
  );
  const authorNodes=role=>[...document.querySelectorAll(messageRoleSelector)]
    .filter(node=>!role||messageRole(node)===role);
  const authorNode=(root,role='')=>{
    if(!root)return null;
    if(messageRole(root)&&(!role||messageRole(root)===role))return root;
    return [...root.querySelectorAll(messageRoleSelector)]
      .find(node=>!role||messageRole(node)===role)||null;
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
