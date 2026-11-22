document.addEventListener("DOMContentLoaded", function () {

  const layout = document.querySelector(".bslib-sidebar-layout");

  const toggle = layout.querySelector(".collapse-toggle");

  const telaDesktop = window.matchMedia("(min-width: 576px)");

  const comecaAberto = !!layout.querySelector(".sidebar.menu-comeca-aberto");
  if (telaDesktop.matches && !comecaAberto) layout.classList.add("mini-sidebar");

  layout.querySelectorAll(".sidebar .action-button, .sidebar .accordion-button").forEach(function (item) {
    const rotulo = item.querySelector(".action-label, .accordion-title");
    if (rotulo && !item.title) item.title = rotulo.textContent.trim();
  });

  toggle.addEventListener(
    "click",
    function (e) {

      if (!telaDesktop.matches) return;

      e.stopImmediatePropagation();

      const fechado = layout.classList.toggle("mini-sidebar");

      if (window.Shiny && Shiny.setInputValue) {
        Shiny.setInputValue("menu_aberto", !fechado, { priority: "event" });
      }
    },
    true
  );

  function cabecalhoDoGrupo(botao) {
    const itemAccordion = botao.closest(".accordion-item");
    if (!itemAccordion) return null;
    return itemAccordion.querySelector(".accordion-button");
  }

  document.querySelectorAll(".sidebar .action-button.selecionado").forEach(function (botao) {
    const cabecalho = cabecalhoDoGrupo(botao);
    if (cabecalho) cabecalho.classList.add("selecionado");
  });

  document.addEventListener("click", function (e) {
    const botao = e.target.closest(".sidebar .action-button");
    if (!botao) return;

    document.querySelectorAll(".sidebar .selecionado").forEach(function (el) {
      el.classList.remove("selecionado");
    });

    botao.classList.add("selecionado");

    const cabecalho = cabecalhoDoGrupo(botao);
    if (cabecalho) cabecalho.classList.add("selecionado");
  });

  window.addEventListener(
    "click",
    function (e) {
      const cabecalho = e.target.closest(".sidebar .accordion-button");
      if (!cabecalho) return;
      const grupo = cabecalho.closest("[data-pagina-do-grupo]");
      if (!grupo) return;
      const botao = document.getElementById(grupo.dataset.paginaDoGrupo);
      if (!botao || botao.classList.contains("selecionado")) return;
      if (!cabecalho.classList.contains("collapsed")) e.stopPropagation();
      botao.click();
    },
    true
  );

  document.addEventListener("show.bs.collapse", function (e) {
    const painel = e.target;
    if (!painel.closest(".sidebar")) return;
    document.querySelectorAll(".sidebar .accordion-collapse.show").forEach(function (outro) {
      if (outro === painel) return;
      bootstrap.Collapse.getOrCreateInstance(outro).hide();
    });
  });
});
