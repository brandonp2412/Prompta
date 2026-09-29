node=>{
  if(!node)return false;
  const composedParent=current=>{
    if(!current)return null;
    if(current.assignedSlot)return current.assignedSlot;
    if(current.parentElement)return current.parentElement;
    const root=current.getRootNode?.();
    return root&&root!==document?root.host||null:null;
  };
  for(let current=node;current&&current.nodeType===Node.ELEMENT_NODE;current=composedParent(current)){
    if(
      current.hidden
      ||current.inert
      ||(current.getAttribute?.('aria-hidden')||'').trim().toLowerCase()==='true'
    )return false;
    try{
      if(current.checkVisibility?.({
        checkOpacity:true,
        checkVisibilityCSS:true,
        contentVisibilityAuto:true
      })===false)return false;
    }catch{}
    const style=getComputedStyle(current);
    if(
      style.display==='none'
      ||style.visibility==='hidden'
      ||style.visibility==='collapse'
      ||Number(style.opacity)===0
      ||style.contentVisibility==='hidden'
    )return false;
  }
  return true;
}
