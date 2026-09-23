root => {
                          const clone=root.cloneNode(true);
                          clone.querySelectorAll('button,[role="button"]').forEach(node=>node.remove());
                          const text=(clone.textContent||'').trim();
                          const suffix=['Show moreShow less','Show lessShow more'].find(v=>text.endsWith(v));
                          return (suffix?text.slice(0,-suffix.length):text).trim();
                        }
