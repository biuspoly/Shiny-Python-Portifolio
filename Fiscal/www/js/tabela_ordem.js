(function () {
  "use strict";

  var CLASSE = "tabela-ordem-valor";
  var SVG = "http://www.w3.org/2000/svg";
  var escolhas = {};

  function nomeDaColuna(th) {
    return (th.textContent || "").replace(/\s+/g, " ").trim();
  }

  function colunasDaCaixa(caixa) {
    try {
      return JSON.parse(caixa.getAttribute("data-ordem-colunas") || "[]");
    } catch (erro) {
      return [];
    }
  }

  function cabecalho(alvo) {
    var th = alvo && alvo.closest ? alvo.closest("thead th") : null;
    if (!th) return null;
    var caixa = th.closest("." + CLASSE);
    var tabela = th.closest("shiny-data-frame[id]");
    if (!caixa || !tabela) return null;

    if (th.closest(".fis-tabela-marcavel") && th.matches("thead tr > th:first-child")) return null;
    if (colunasDaCaixa(caixa).indexOf(nomeDaColuna(th)) < 0) return null;
    return { th: th, tabela: tabela };
  }

  function pedirOrdem(evento) {
    var achado = cabecalho(evento.target);
    if (!achado) return;
    evento.preventDefault();
    evento.stopPropagation();
    if (!window.Shiny || !Shiny.setInputValue) return;
    Shiny.setInputValue(achado.tabela.id + "_ordem", { coluna: nomeDaColuna(achado.th) }, { priority: "event" });
  }

  document.addEventListener("click", pedirOrdem, true);

  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Enter" || evento.key === " ") pedirOrdem(evento);
  }, true);

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
        return;
      }
      var desc = escolha.desc ? "1" : "0";
      if (seta && seta.getAttribute("data-desc") === desc) return;
      if (seta) seta.remove();

      (th.firstElementChild || th).appendChild(criarSeta(escolha.desc));
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

  function registrar() {
    if (!(window.Shiny && Shiny.addCustomMessageHandler)) {
      setTimeout(registrar, 50);
      return;
    }
    Shiny.addCustomMessageHandler("tabelaOrdem", function (mensagem) {
      escolhas[mensagem.id] = mensagem.coluna ? { coluna: mensagem.coluna, desc: !!mensagem.desc } : null;

      algumaSeta = true;
      repintar();
    });
  }
  registrar();

  document.addEventListener("DOMContentLoaded", function () {
    new MutationObserver(repintar).observe(document.body, { childList: true, subtree: true });
  });
})();
