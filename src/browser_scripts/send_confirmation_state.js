() => {
    const main = document.querySelector('main');
    if (!main) return null;
    const visible = element => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    };
    const editors = Array.from(main.querySelectorAll(
        'textarea,[role="textbox"],[contenteditable="true"]'
    )).filter(visible);
    if (editors.length !== 1) return null;
    const editor = editors[0];
    const composer = ('value' in editor ? editor.value : editor.innerText) || '';
    const generating = Array.from(main.querySelectorAll('button,[role="button"]'))
        .some(button => visible(button) && /^stop generating$/i.test(
            (button.getAttribute('aria-label') || button.getAttribute('title') ||
            button.textContent || '').trim()
        ));
    return {composer_text: composer, send_in_progress: generating};
}
