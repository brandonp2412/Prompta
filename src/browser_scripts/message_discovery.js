  const messageRoleSelector=__MESSAGE_ROLE_SELECTOR__;
  const assistantSelector=__ASSISTANT_SELECTOR__;
  const semanticTurnSelector=__SEMANTIC_TURN_SELECTOR__;
  const legacyTurnSelector=__LEGACY_TURN_SELECTOR__;
  const composedParent=node=>{
    if(!node)return null;
    if(node.assignedSlot)return node.assignedSlot;
    if(node.parentElement)return node.parentElement;
    const root=node.getRootNode?.();
    return root&&root!==document?root.host||null:null;
  };
  const composedChildNodes=node=>{
    if(!node)return [];
    if(node.tagName==='SLOT'){
      const assigned=node.assignedNodes?.({flatten:true})||[];
      if(assigned.length)return [...assigned];
    }
    if(node.shadowRoot)return [...node.shadowRoot.childNodes];
    return [...(node.childNodes||[])];
  };
  const composedChildren=node=>composedChildNodes(node)
    .filter(child=>child.nodeType===Node.ELEMENT_NODE);
  const composedTextContent=node=>{
    if(!node)return '';
    if(node.nodeType===Node.TEXT_NODE)return node.nodeValue||'';
    return composedChildNodes(node).map(composedTextContent).join('');
  };
  const deepQueryAll=(root,selector)=>{
    if(!root)return [];
    const matches=[];
    const walk=scope=>{
      for(const child of composedChildren(scope)){
        if(child.matches?.(selector))matches.push(child);
        walk(child);
      }
    };
    walk(root);
    return matches;
  };
  const deepContains=(ancestor,node)=>{
    if(!ancestor||!node)return false;
    for(let current=node;current;current=composedParent(current)){
      if(current===ancestor)return true;
    }
    return false;
  };
  const deepClosest=(node,selector)=>{
    for(let current=node;current;current=composedParent(current)){
      if(current.matches?.(selector))return current;
    }
    return null;
  };
  const referencedElement=(node,id)=>{
    const seenRoots=new Set();
    for(let current=node;current;current=composedParent(current)){
      const root=current.getRootNode?.();
      if(!root||seenRoots.has(root))continue;
      seenRoots.add(root);
      const match=root.getElementById?.(id);
      if(match)return match;
    }
    return document.getElementById(id);
  };
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
    const leading=label.match(/^(you|user|human|chatgpt|assistant|model|bot)(?:\s+(?:said|wrote|asked|answered|responded|replied|message|response|reply|prompt|turn))?\s*:?$/i);
    if(leading)return normaliseRole(leading[1]);
    const relational=label.match(/^(?:message|response|reply|prompt|turn|answer)\s+(?:from|by)\s+(you|user|human|chatgpt|assistant|model|bot)\s*:?$/i);
    return normaliseRole(relational?.[1]);
  };
  const referencedText=(node,attributeName)=>String(node?.getAttribute?.(attributeName)||'')
    .split(/\s+/)
    .filter(Boolean)
    .map(id=>composedTextContent(referencedElement(node,id)))
    .join(' ')
    .replace(/\s+/g,' ')
    .trim();
  const labelledByText=node=>referencedText(node,'aria-labelledby');
  const describedByText=node=>referencedText(node,'aria-describedby');
  const accessibleName=node=>String(
    node?.getAttribute?.('aria-label')
    ||labelledByText(node)
    ||node?.getAttribute?.('title')
    ||''
  ).replace(/\s+/g,' ').trim();
  const semanticInteractiveControlSelector=[
    'button',
    'summary',
    'input:not([type="hidden"])',
    'select',
    'textarea',
    '[contenteditable="true"]',
    '[role="button"]',
    '[role="checkbox"]',
    '[role="combobox"]',
    '[role="listbox"]',
    '[role="menuitem"]',
    '[role="menuitemcheckbox"]',
    '[role="menuitemradio"]',
    '[role="option"]',
    '[role="radio"]',
    '[role="searchbox"]',
    '[role="slider"]',
    '[role="spinbutton"]',
    '[role="switch"]',
    '[role="tab"]',
    '[role="treeitem"]',
    '[aria-controls]',
    '[aria-expanded]',
    '[aria-pressed]',
    '[aria-checked]'
  ].join(',');
  const focusableInteractiveSelector='[tabindex]:not([tabindex="-1"])';
  const isFocusableInteractiveControl=node=>{
    if(!node?.matches?.(focusableInteractiveSelector))return false;
    const name=accessibleName(node);
    return Boolean(name&&!accessibleRole(name));
  };
  const semanticInteractiveControls=root=>{
    if(!root?.querySelectorAll)return [];
    return [...new Set([
      ...deepQueryAll(root,semanticInteractiveControlSelector),
      ...deepQueryAll(root,focusableInteractiveSelector)
        .filter(isFocusableInteractiveControl)
    ])];
  };
  const isSemanticInteractiveControl=node=>Boolean(
    node?.matches?.(semanticInteractiveControlSelector)
    ||isFocusableInteractiveControl(node)
  );
  // Action-state discovery must tolerate more tag/role churn than transcript
  // stripping. Keep ordinary answer links out of the stripping selector while
  // still recognizing link-like controls that carry explicit action semantics.
  const semanticActionControlSelector=[
    semanticInteractiveControlSelector,
    'a[href][aria-label]',
    'a[href][aria-labelledby]',
    'a[href][aria-describedby]',
    'a[href][title]',
    'select',
    'input:not([type="hidden"])',
    '[role="link"]',
    '[aria-controls]',
    '[aria-haspopup]',
    '[aria-expanded]',
    '[aria-pressed]',
    '[aria-checked]',
    '[aria-selected]'
  ].join(',');
  const semanticActionControls=root=>{
    if(!root?.querySelectorAll)return [];
    return [...new Set([
      ...deepQueryAll(root,semanticActionControlSelector),
      ...deepQueryAll(root,focusableInteractiveSelector)
        .filter(isFocusableInteractiveControl)
    ])];
  };
  const isSemanticActionControl=node=>Boolean(
    node?.matches?.(semanticActionControlSelector)
    ||isFocusableInteractiveControl(node)
  );
  const accessibleNodeRole=node=>[
    node?.getAttribute?.('aria-label')||'',
    labelledByText(node),
    describedByText(node),
    node?.getAttribute?.('aria-roledescription')||'',
    node?.getAttribute?.('title')||''
  ].map(accessibleRole).find(Boolean)||'';
  const transcriptLandmarkSelector='main,[role="main"],[role="log"],[role="feed"]';
  const isTranscriptLandmark=node=>Boolean(node&&(
    node.tagName==='MAIN'||['main','log','feed'].includes(String(node.getAttribute?.('role')||'').toLowerCase())
  ));
  const semanticHeadingSelector='h1,h2,h3,h4,h5,h6,[role="heading"],[aria-level]';
  const headingNodes=root=>root?.querySelectorAll
    ?deepQueryAll(root,semanticHeadingSelector)
    :[];
  const headingAccessibleRole=heading=>accessibleNodeRole(heading)
    ||accessibleRole(composedTextContent(heading));
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
      let candidate=composedParent(heading)||heading;
      for(let parent=composedParent(candidate);parent&&parent!==document.body;parent=composedParent(parent)){
        if(isTranscriptLandmark(parent))break;
        const headings=headingNodes(parent)
          .filter(node=>headingAccessibleRole(node));
        if(headings.length!==1||headings[0]!==heading)break;
        candidate=parent;
      }
      return candidate;
    });
  };
  const isHeadingNode=node=>Boolean(node?.matches?.(semanticHeadingSelector));
  const semanticMessageText=root=>{
    const walk=node=>{
      if(!node)return '';
      if(node.nodeType===Node.TEXT_NODE)return node.nodeValue||'';
      if(node!==root&&isSemanticInteractiveControl(node))return '';
      if(node!==root&&isHeadingNode(node)&&headingAccessibleRole(node))return '';
      return composedChildNodes(node).map(walk).join('');
    };
    return walk(root).trim();
  };
  const directMessageRole=node=>normaliseRole(
    node?.getAttribute?.('data-message-author-role')
    ||semanticAttribute(
      node,
      /(?:^|-)(?:(?:message-)?(?:author|speaker|actor|participant)-role|message-role)$/i,
      [['author','speaker','actor','participant'],['role']]
    )
    ||semanticAttribute(
      node,
      /(?:^|-)(?:(?:message|turn)-)?(?:author|speaker|sender|actor|participant)$/i,
      [['author','speaker','sender','actor','participant']]
    )
  )||semanticSearchRole(node)
    ||(!isHeadingNode(node)?accessibleNodeRole(node):'');
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
    for(const node of deepQueryAll(root,'*')){
      const id=messageId(node);
      if(id)return id;
    }
    return '';
  };
  let documentOrderIndex=null;
  const documentOrder=(left,right)=>{
    if(left===right)return 0;
    if(!documentOrderIndex){
      documentOrderIndex=new Map(deepQueryAll(document,'*').map((node,index)=>[node,index]));
    }
    const leftIndex=documentOrderIndex.get(left);
    const rightIndex=documentOrderIndex.get(right);
    if(leftIndex!==undefined&&rightIndex!==undefined&&leftIndex!==rightIndex){
      return leftIndex-rightIndex;
    }
    return left.compareDocumentPosition(right)&Node.DOCUMENT_POSITION_FOLLOWING?-1:1;
  };
  const innermostRoleNodes=nodes=>nodes.filter(node=>!nodes.some(other=>
    other!==node
    &&deepContains(node,other)
    &&messageRole(other)===messageRole(node)
  ));
  const commonAncestor=(left,right)=>{
    if(!left||!right)return null;
    const ancestors=new Set();
    for(let node=left;node;node=composedParent(node))ancestors.add(node);
    for(let node=right;node;node=composedParent(node)){
      if(ancestors.has(node))return node;
    }
    return null;
  };
  const nodeDepth=node=>{
    let depth=0;
    for(let current=node;current;current=composedParent(current))depth+=1;
    return depth;
  };
  const inferredTranscriptRoot=()=>{
    const pageRoot=document.body||document.documentElement;
    if(!pageRoot)return document.documentElement;
    const roleNodes=innermostRoleNodes([...new Set([
      ...deepQueryAll(pageRoot,messageRoleSelector),
      ...deepQueryAll(pageRoot,semanticTurnSelector),
      ...deepQueryAll(pageRoot,'*').filter(node=>directMessageRole(node)),
      ...headingMessageNodes(pageRoot)
    ])].filter(node=>messageRole(node))).sort(documentOrder);
    const candidates=[];
    for(let index=1;index<roleNodes.length;index+=1){
      const left=roleNodes[index-1];
      const right=roleNodes[index];
      if(messageRole(left)===messageRole(right))continue;
      const root=commonAncestor(left,right);
      if(root&&root!==pageRoot&&root!==document.documentElement)candidates.push(root);
    }
    if(!candidates.length)return pageRoot;
    const profile=root=>{
      const roles=roleNodes.filter(node=>deepContains(root,node)).map(messageRole);
      let pairs=0;
      let unmatched=0;
      let pendingUser=false;
      for(const role of roles){
        if(role==='user'){
          if(pendingUser)unmatched+=1;
          pendingUser=true;
          continue;
        }
        if(role==='assistant'){
          if(pendingUser){pairs+=1;pendingUser=false;}
          else unmatched+=1;
        }
      }
      if(pendingUser)unmatched+=1;
      return {
        root,
        pairs,
        unmatched,
        startsUser:roles[0]==='user'?1:0,
        count:roles.length,
        depth:nodeDepth(root)
      };
    };
    return [...new Set(candidates)]
      .map(profile)
      .sort((left,right)=>
        right.pairs-left.pairs
        ||left.unmatched-right.unmatched
        ||right.startsUser-left.startsUser
        ||right.count-left.count
        ||right.depth-left.depth
      )[0]?.root
      ||pageRoot;
  };
  const transcriptRoot=()=>{
    const score=root=>{
      const semantic=deepQueryAll(root,messageRoleSelector+','+semanticTurnSelector).length;
      const structural=deepQueryAll(root,'*').filter(node=>directMessageRole(node)).length;
      const headings=headingNodes(root).filter(node=>headingAccessibleRole(node)).length;
      return semantic*4+structural*2+headings;
    };
    const landmarks=deepQueryAll(document,transcriptLandmarkSelector);
    if(!landmarks.length)return inferredTranscriptRoot();
    const best=landmarks
      .map((root,index)=>({root,index,score:score(root)}))
      .sort((left,right)=>right.score-left.score||left.index-right.index)[0];
    const inferred=inferredTranscriptRoot();
    if(
      inferred
      &&inferred!==document.body
      &&inferred!==document.documentElement
      &&inferred!==best.root
    ){
      const inferredRoles=new Set([
        inferred,
        ...deepQueryAll(inferred,messageRoleSelector),
        ...deepQueryAll(inferred,semanticTurnSelector),
        ...deepQueryAll(inferred,'*').filter(node=>directMessageRole(node)),
        ...headingMessageNodes(inferred)
      ].map(node=>messageRole(node)).filter(Boolean));
      const coherentDescendant=deepContains(best.root,inferred)
        &&inferredRoles.has('user')
        &&inferredRoles.has('assistant');
      if(coherentDescendant||score(inferred)>best.score)return inferred;
    }
    return best.root;
  };
  const messageNodes=()=>{
    const root=transcriptRoot();
    const primary=innermostRoleNodes([...new Set([
      ...deepQueryAll(root,messageRoleSelector),
      ...deepQueryAll(root,semanticTurnSelector)
    ])].filter(node=>messageRole(node)));
    const roles=new Set(primary.map(messageRole));
    // Always inspect structural role metadata too. During staggered DOM rollouts a page can
    // contain both the established namespace and a renamed one; stopping once both roles
    // are seen in the established markup would silently drop turns using the new namespace.
    const structural=innermostRoleNodes(
      deepQueryAll(root,'*').filter(node=>directMessageRole(node))
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
      &&(existing===node||deepContains(existing,node)||deepContains(node,existing))
    );
    const legacy=deepQueryAll(root,legacyTurnSelector)
      .filter(node=>!deepQueryAll(node,primarySelector).length)
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
      ...deepQueryAll(root,messageRoleSelector),
      ...deepQueryAll(root,semanticTurnSelector)
    ])].filter(node=>messageRole(node)));
    const structural=innermostRoleNodes(
      deepQueryAll(root,'*').filter(node=>directMessageRole(node))
    );
    return [...new Set([...primary,...structural])].sort(documentOrder);
  };
  const authorNode=(root,role='')=>{
    if(!root)return null;
    if(messageRole(root)&&(!role||messageRole(root)===role))return root;
    return descendantAuthorNodes(root)
      .find(node=>!role||messageRole(node)===role)||null;
  };
  const semanticTurnContainer=node=>{
    for(let candidate=node;candidate&&candidate!==document.body;candidate=composedParent(candidate)){
      const turnKey=semanticAttribute(
        candidate,
        /(?:^|-)turn-key$/i,
        [['turn'],['key']]
      );
      if(turnKey)return candidate;
      if(candidate!==node&&isTranscriptLandmark(candidate))break;
    }
    return null;
  };
  const semanticTurnRoot=node=>semanticTurnContainer(node)
    ||deepClosest(node,semanticTurnSelector)
    ||null;
  const structuralTurnRoot=node=>{
    if(!node)return null;
    let candidate=null;
    for(let parent=composedParent(node);parent&&parent!==document.body;parent=composedParent(parent)){
      if(isTranscriptLandmark(parent))break;
      const authors=descendantAuthorNodes(parent);
      if(authors.length!==1||authors[0]!==node)break;
      candidate=parent;
    }
    return candidate;
  };
  const legacyTurnRoot=node=>deepClosest(node,legacyTurnSelector)||null;
  const turnRoot=node=>semanticTurnRoot(node)
    ||structuralTurnRoot(node)
    ||legacyTurnRoot(node)
    ||node
    ||null;
  const turnMessageId=(turn,role='')=>messageId(turn)
    ||messageId(authorNode(turn,role))
    ||descendantMessageId(turn)
    ||'';
