(()=>{
/*__TRANSCRIPT_BROWSER_ENGINE__*/
  const root=promptaTranscriptEngine.latestAssistantRoot();
  return promptaTranscriptEngine.reactSnapshot(
    root,
    'chromium-tool-enrichment',
    {stringLimit:20000,partsLimit:8}
  );
})()
