document.addEventListener('DOMContentLoaded', function () {
  const expansionRepo = 'https://github.com/pdm-project/pdm-expansions';
  const expansionsApi = 'https://pdm-expansions.vercel.app/api/sample';
  const el = document.querySelector('a.pdm-expansions');

  function loadExpansions() {
    fetch(expansionsApi, { mode: 'cors', redirect: 'follow' })
      .then((response) => {
        console.log(response);
        return response.json();
      })
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
