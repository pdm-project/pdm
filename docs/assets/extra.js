document.addEventListener('DOMContentLoaded', function () {
  function isLatestDocsPath() {
    return window.location.pathname.includes('/latest/');
  }

  function injectLatestDocsBanner() {
    if (!isLatestDocsPath()) return;
    if (document.querySelector('.pdm-latest-docs-banner')) return;

    const content = document.querySelector('.md-content__inner');
    if (!content) return;

    const banner = document.createElement('div');
    banner.className = 'admonition warning pdm-latest-docs-banner';
    banner.innerHTML = [
      '<p class="admonition-title">Latest docs</p>',
      '<p>This documentation is kept in sync with the main branch. It may describe features that are not available in the latest released version.</p>',
    ].join('');

    content.insertBefore(banner, content.firstChild);
  }

  injectLatestDocsBanner();

  const expansionRepo = 'https://github.com/pdm-project/pdm-expansions';
  const expansionsApi = 'https://expansion.pdm-project.org/api/sample';
  const el = document.querySelector('a.pdm-expansions');
  if (!el) return;

  function loadExpansions() {
    fetch(expansionsApi, { mode: 'cors', redirect: 'follow' })
      .then((response) => response.json())
      .then((data) => {
        window.expansionList = data.data;
        setExpansion();
      });
  }

  function setExpansion() {
    const { expansionList } = window;
    if (!expansionList || !expansionList.length) {
      window.location.href = expansionRepo;
      return;
    }
    const expansion = expansionList[expansionList.length - 1];
    expansionList.splice(expansionList.length - 1, 1);
    el.innerText = expansion;
    if (el.style.display == 'none') {
      el.style.display = '';
    }
  }

  loadExpansions();
  el.addEventListener('click', function (e) {
    e.preventDefault();
    setExpansion();
  });
});
