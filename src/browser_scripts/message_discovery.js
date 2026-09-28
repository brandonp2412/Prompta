  const messageRoleSelector=__MESSAGE_ROLE_SELECTOR__;
  const assistantSelector=__ASSISTANT_SELECTOR__;
  const semanticTurnSelector=__SEMANTIC_TURN_SELECTOR__;
  const legacyTurnSelector=__LEGACY_TURN_SELECTOR__;
  const normaliseAttributeName=value=>String(value||'')
    .trim()
    .toLowerCase()
    .replace(/[_:]+/g,'-')
    .replace(/-+/g,'-');
  const semanticAttribute=(node,namePattern,tokenGroups=[])=>{
    if(!node?.attributes)return '';
    for(const attribute of node.attributes){
      const name=normaliseAttributeName(attribute.name);
      if(namePattern.test(name))return String(attribute.value||'');
      if(!tokenGroups.length)continue;
      const tokens=new Set(name.split('-').filter(Boolean));
      if(tokenGroups.every(group=>group.some(token=>tokens.has(token)))){
        return String(attribute.value||'');
      }
    }
    return '';
  };
  const normaliseRole=value=>{
    const role=String(value||'').replace(/\s+/g,' ').trim().toLowerCase();
    const tokens=role.split(/[^a-z0-9]+/).filter(Boolean);
    if(tokens.some(token=>/^(?:user|human|you)$/.test(token)))return 'user';
    if(tokens.some(token=>/^(?:assistant|chatgpt|model|bot)$/.test(token)))return 'assistant';
    return '';
  };
  const semanticSearchRole=node=>{
    const key=semanticAttribute(
      node,
      /(?:^|-)search-unit-key$/i,
      [['search'],['unit'],['key']]
    );
    const tokens=String(key||'').split(/[^a-z0-9]+/i).filter(Boolean);
    for(const token of tokens){
      const role=normaliseRole(token);
      if(role)return role;
    }
    return '';
  };
  const accessibleRole=value=>{
    const label=String(value||'').replace(/\s+/g,' ').trim();
    const match=label.match(/^(you|user|human|chatgpt|assistant|model|bot)(?:\s+(?:said|wrote|asked|answered|responded|replied|message|response|reply|prompt|turn))?\s*:?$/i);
    return normaliseRole(match?.[1]);
  };
  const accessibleName=node=>{
    const label=String(node?.getAttribute?.('aria-label')||'').trim();
    if(label)return label;
    const labelledBy=String(node?.getAttribute?.('aria-labelledby')||'')
      .split(/\s+/)
      .filter(Boolean);
    if(!labelledBy.length)return '';
    return labelledBy
      .map(id=>document.getElementById(id)?.textContent||'')
      .join(' ')
      .replace(/\s+/g,' ')
      .trim();
  };
  const headingNodes=root=>root?.querySelectorAll
    ?[...root.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]')]
    :[];
  const headingAccessibleRole=heading=>accessibleRole(accessibleName(heading))
    ||accessibleRole(heading?.textContent);
  const headingRole=node=>{
    for(const heading of headingNodes(node)){
      const role=headingAccessibleRole(heading);
      if(role)return role;
    }
    return '';
  };
  const headingMessageNodes=root=>{
    if(!root?.querySelectorAll)return [];
    const roleHeadings=headingNodes(root)
      .filter(heading=>headingAccessibleRole(heading));
    return roleHeadings.map(heading=>{
      let candidate=heading.parentElement||heading;
      for(let parent=candidate.parentElement;parent&&parent!==document.body;parent=parent.parentElement){
        if(parent.tagName==='MAIN'||parent.getAttribute?.('role')==='main')break;
        const headings=headingNodes(parent)
          .filter(node=>headingAccessibleRole(node));
        if(headings.length!==1||headings[0]!==heading)break;
        candidate=parent;
      }
      return candidate;
    });
  };
  const isHeadingNode=node=>Boolean(node?.matches?.('h1,h2,h3,h4,h5,h6,[role="heading"]'));
  const directMessageRole=node=>normaliseRole(
    node?.getAttribute?.('data-message-author-role')
    ||semanticAttribute(
      node,
      /(?:^|-)(?:(?:message-)?(?:author|speaker)-role|message-role)$/i,
      [['author','speaker'],['role']]
    )
    ||semanticAttribute(
      node,
      /(?:^|-)(?:(?:message|turn)-)?(?:author|speaker|sender)$/i,
      [['author','speaker','sender']]
    )
  )||semanticSearchRole(node)
    ||(!isHeadingNode(node)?accessibleRole(accessibleName(node)):'');
  const messageRole=node=>directMessageRole(node)||headingRole(node);
  const searchMessageIds=node=>semanticAttribute(
    node,
    /(?:^|-)search-message-ids$/i,
    [['search'],['message'],['id','ids']]
  ).split(/\s+/).filter(Boolean);
  const messageId=node=>String(
    node?.getAttribute?.('data-message-id')
    ||node?.getAttribute?.('data-message-uuid')
    ||semanticAttribute(
      node,
      /(?:^|-)(?:selection-)?message-(?:id|uuid)$/i,
      [['message'],['id','uuid']]
    )
    ||semanticAttribute(
      node,
      /(?:^|-)(?:(?:conversation-)?turn)-(?:id|uuid)$/i,
      [['turn'],['id','uuid']]
    )
    ||searchMessageIds(node).at(-1)
    ||''
  );
  const descendantMessageId=root=>{
    if(!root?.querySelectorAll)return '';
    for(const node of root.querySelectorAll('*')){
      const id=messageId(node);
      if(id)return id;
    }
    return '';
  };
  const documentOrder=(left,right)=>left===right?0:(
    left.compareDocumentPosition(right)&Node.DOCUMENT_POSITION_FOLLOWING?-1:1
  );
  const innermostRoleNodes=nodes=>nodes.filter(node=>!nodes.some(other=>
    other!==node
    &&node.contains(other)
    &&messageRole(other)===messageRole(node)
  ));
  const transcriptRoot=()=>{
    const landmarks=[...document.querySelectorAll('main,[role="main"]')];
    if(!landmarks.length)return document.body||document.documentElement;
    const score=root=>{
      const semantic=root.querySelectorAll(messageRoleSelector+','+semanticTurnSelector).length;
      const structural=[...root.querySelectorAll('*')].filter(node=>directMessageRole(node)).length;
      const headings=headingNodes(root).filter(node=>headingAccessibleRole(node)).length;
      return semantic*4+structural*2+headings;
    };
    return landmarks
      .map((root,index)=>({root,index,score:score(root)}))
      .sort((left,right)=>right.score-left.score||left.index-right.index)[0]?.root
      ||landmarks[0];
  };
  const messageNodes=()=>{
    const primary=innermostRoleNodes([...new Set([
      ...document.querySelectorAll(messageRoleSelector),
      ...document.querySelectorAll(semanticTurnSelector)
    ])].filter(node=>messageRole(node)));
    const roles=new Set(primary.map(messageRole));
    const root=transcriptRoot();
    // Always inspect structural role metadata too. During staggered DOM rollouts a page can
    // contain both the established namespace and a renamed one; stopping once both roles
    // are seen in the established markup would silently drop turns using the new namespace.
    const structural=innermostRoleNodes(
      [...root.querySelectorAll('*')].filter(node=>directMessageRole(node))
    );
    const headingCandidates=headingMessageNodes(root);
    const recoverableRoles=new Set([
      ...roles,
      ...headingCandidates.map(messageRole).filter(Boolean)
    ]);
    const headingStructural=recoverableRoles.has('user')&&recoverableRoles.has('assistant')
      ?headingCandidates
      :[];
    const primarySelector=messageRoleSelector+','+semanticTurnSelector;
    const overlapsPrimary=node=>primary.some(existing=>
      messageRole(existing)===messageRole(node)
      &&(existing===node||existing.contains(node)||node.contains(existing))
    );
    const legacy=[...document.querySelectorAll(legacyTurnSelector)]
      .filter(node=>!node.querySelector(primarySelector))
      .filter(node=>messageRole(node));
    const fallback=[...structural,...headingStructural,...legacy]
      .filter(node=>messageRole(node))
      .filter(node=>!overlapsPrimary(node));
    return [...new Set([...primary,...fallback])].sort(documentOrder);
  };
  const authorNodes=role=>messageNodes()
    .filter(node=>!role||messageRole(node)===role);
  const descendantAuthorNodes=root=>{
    if(!root?.querySelectorAll)return [];
    const primary=innermostRoleNodes([...new Set([
      ...root.querySelectorAll(messageRoleSelector),
      ...root.querySelectorAll(semanticTurnSelector)
    ])].filter(node=>messageRole(node)));
    const structural=innermostRoleNodes(
      [...root.querySelectorAll('*')].filter(node=>directMessageRole(node))
    );
    return [...new Set([...primary,...structural])].sort(documentOrder);
  };
  const authorNode=(root,role='')=>{
    if(!root)return null;
    if(messageRole(root)&&(!role||messageRole(root)===role))return root;
    return descendantAuthorNodes(root)
      .find(node=>!role||messageRole(node)===role)||null;
  };
  const semanticTurnRoot=node=>node?.closest?.(semanticTurnSelector)||null;
  const structuralTurnRoot=node=>{
    if(!node)return null;
    let candidate=null;
    for(let parent=node.parentElement;parent&&parent!==document.body;parent=parent.parentElement){
      if(parent.tagName==='MAIN'||parent.getAttribute?.('role')==='main')break;
      const authors=descendantAuthorNodes(parent);
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
    ||descendantMessageId(turn)
    ||'';
