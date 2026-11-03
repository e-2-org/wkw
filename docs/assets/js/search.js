/*
 * Search, as WordPress did it: the names with a page, matched on their name, other names,
 * professions and bio. Every word has to match. Results whose name matches come first, then
 * the rest, alphabetically, each shown like WordPress's search results (an excerpt and a link).
 * ?q= holds the search, as WordPress's ?s= did.
 */
(function () {
    const box = document.getElementById('search-results');
    const base = box.dataset.base;
    const q = (new URLSearchParams(location.search).get('q') || '').trim();
    const fold = s => s.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const esc = s => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
    const excerpt = text => {
        const w = text.split(/\s+/);
        return w.slice(0, 30).join(' ') + (w.length > 30 ? ' ...' : '');
    };
    document.querySelectorAll('.navigation-search .search-field').forEach(f => { f.value = q; });

    function searchForm(value) {
        return `<form method="get" class="search-form" action="${base}search/"><label>
            <span class="screen-reader-text">Search for:</span>
            <input type="search" class="search-field" placeholder="Search &hellip;" value="${esc(value)}" name="q" title="Search for:">
            </label> <input type="submit" class="search-submit" value="Search"></form>`;
    }

    function nothing() {
        document.title = 'Nothing found – Who Knew Whom';
        box.innerHTML = `<div class="no-results not-found"><div class="inside-article">
            <header class="entry-header"><h1 class="entry-title">Nothing Found</h1></header>
            <div class="wkwname-meta"></div><div class="entry-content">
            <p>Sorry, but nothing matched your search terms. Please try again with some different keywords.</p>
            ${searchForm(q)}</div></div></div>`;
    }

    function article([id, name, alt, professions, dates, bio]) {
        const url = `${base}names/${id}/`;
        const meta = [
            alt ? `<div class="wkw-aka-name"><p>${esc(alt)}</p></div>` : '',
            professions.length ? `<div class="wkw-professions"><p>${professions.map(([p, slug]) =>
                `<a href="${base}types/${slug}/" title="View others: ${esc(p)}">${esc(p)}</a>`).join(', ')}</p></div>` : '',
            dates ? `<div class="wkw-birth-death"><p>${esc(dates)}</p></div>` : '',
        ].join('');
        return `<article class="${id} wkwname type-wkwname status-publish hentry"><div class="inside-article">
            <header class="entry-header"><h2 class="entry-title"><a href="${url}" rel="bookmark">${esc(name)}</a></h2></header>
            <div class="wkwname-meta">${meta}</div>
            <div class="entry-content"><p>${esc(excerpt(bio))} <a title="${esc(name)}" class="read-more" href="${url}"
                aria-label="Read more about ${esc(name)}">Read more</a></p></div></div></article>`;
    }

    if (!q) return nothing();
    document.title = `Search Results for “${q}” – Who Knew Whom`;
    fetch(box.dataset.index).then(r => r.json()).then(people => {
        const words = fold(q).split(/\s+/).filter(Boolean);
        const found = [];
        for (const p of people) {
            const [, name, alt, professions, dates, bio] = p;
            const title = fold(name + ' ' + alt);
            const all = title + ' ' + fold(professions.map(x => x[0]).join(' ') + ' ' + dates + ' ' + bio);
            if (words.every(w => all.includes(w))) found.push([words.every(w => title.includes(w)) ? 0 : 1, p]);
        }
        if (!found.length) return nothing();
        found.sort((a, b) => a[0] - b[0] || a[1][1].localeCompare(b[1][1]));
        box.innerHTML = `<header class="page-header"><h1 class="page-title">Search Results for: <span>${esc(q)}</span></h1></header>`
            + found.map(f => article(f[1])).join('');
    });
})();
