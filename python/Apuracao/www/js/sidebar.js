document.addEventListener("DOMContentLoaded", function () {

  const layout = document.querySelector(".bslib-sidebar-layout");

  const toggle = layout.querySelector(".collapse-toggle");

  const telaDesktop = window.matchMedia("(min-width: 576px)");

  if (telaDesktop.matches) layout.classList.add("mini-sidebar");

  toggle.addEventListener(
    "click",
    function (e) {

      if (!telaDesktop.matches) return;

      e.stopImmediatePropagation();

      layout.classList.toggle("mini-sidebar");
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

  document.addEventListener("show.bs.collapse", function (e) {
    const painel = e.target;
    if (!painel.closest(".sidebar")) return;
    document.querySelectorAll(".sidebar .accordion-collapse.show").forEach(function (outro) {
      if (outro === painel) return;
      bootstrap.Collapse.getOrCreateInstance(outro).hide();
    });
  });
});
