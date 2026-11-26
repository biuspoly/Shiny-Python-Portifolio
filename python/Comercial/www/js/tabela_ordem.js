(function () {
  "use strict";

  var CLASSE = "tabela-ordem-valor";
  var SVG = "http://www.w3.org/2000/svg";
  var escolhas = {};
  var mousedownNaAlca = false;

  function nomeDaColuna(th) {
    return (th.textContent || "").replace(/\s+/g, " ").trim();
  }

  function cabecalho(alvo) {
    var th = alvo && alvo.closest ? alvo.closest("thead th") : null;
    if (!th || !th.closest("." + CLASSE)) return null;
    var tabela = th.closest("shiny-data-frame[id]");
    return tabela ? { th: th, tabela: tabela } : null;
  }

  function pedirOrdem(evento) {
    var achado = cabecalho(evento.target);
    if (!achado) return;
    evento.preventDefault();
    evento.stopPropagation();

    if (mousedownNaAlca || achado.th.classList.contains("header-html")) return;
    if (!window.Shiny || !Shiny.setInputValue) return;
    Shiny.setInputValue(
      achado.tabela.id + "_ordem",
      { coluna: nomeDaColuna(achado.th) },
      { priority: "event" }
    );
  }

  document.addEventListener(
    "mousedown",
    function (evento) {
      mousedownNaAlca = !!(evento.target.closest && evento.target.closest(".tabela-resize-handle"));
    },
    true
  );
  document.addEventListener("click", pedirOrdem, true);

  document.addEventListener(
    "keydown",
    function (evento) {
      if (evento.key === "Enter" || evento.key === " ") pedirOrdem(evento);
    },
    true
  );

  function criarSeta(desc) {
    var seta = document.createElementNS(SVG, "svg");
    seta.setAttribute("class", "tabela-ordem-seta");
    seta.setAttribute("viewBox", "-1.4 -1.4 2.8 2.8");
    seta.setAttribute("aria-hidden", "true");
    seta.setAttribute("data-desc", desc ? "1" : "0");
    var traco = document.createElementNS(SVG, "path");
    traco.setAttribute("d", desc ? "M -1 -0.5 L 0 0.5 L 1 -0.5" : "M -1 0.5 L 0 -0.5 L 1 0.5");
    seta.appendChild(traco);
    return seta;
  }

  function pintar(tabela) {
    var escolha = escolhas[tabela.id];
    tabela.querySelectorAll("thead th").forEach(function (th) {
      var seta = th.querySelector(".tabela-ordem-seta");
      if (!escolha || nomeDaColuna(th) !== escolha.coluna) {
        if (seta) seta.remove();
        if (th.hasAttribute("aria-sort")) th.removeAttribute("aria-sort");
        return;
      }
      var desc = escolha.desc ? "1" : "0";
      if (seta && seta.getAttribute("data-desc") === desc) return;
      if (seta) seta.remove();

      (th.firstElementChild || th).appendChild(criarSeta(escolha.desc));
      th.setAttribute("aria-sort", escolha.desc ? "descending" : "ascending");
    });
  }

  var agendado = false;
  var algumaSeta = false;
  function repintar() {
    if (agendado || !algumaSeta) return;
    agendado = true;
    window.requestAnimationFrame(function () {
      agendado = false;
      document.querySelectorAll("." + CLASSE + " shiny-data-frame[id]").forEach(pintar);
      algumaSeta = Object.keys(escolhas).some(function (id) { return escolhas[id]; });
    });
  }

  Shiny.addCustomMessageHandler("tabelaOrdem", function (mensagem) {
    escolhas[mensagem.id] = mensagem.coluna ? { coluna: mensagem.coluna, desc: !!mensagem.desc } : null;

    algumaSeta = true;
    repintar();
  });

  document.addEventListener("DOMContentLoaded", function () {
    new MutationObserver(repintar).observe(document.body, { childList: true, subtree: true });
  });
})();
