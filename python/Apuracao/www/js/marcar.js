(function () {
  var MAC = /^mac/i.test((navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform);
  var CABECALHO = ".fis-tabela-marcavel thead tr > th:first-child";

  document.addEventListener("mousedown", function (evento) {
    if (!evento.isTrusted || evento.button !== 0) return;
    if (evento.target.closest && evento.target.closest(CABECALHO)) {
      evento.stopPropagation();
      evento.preventDefault();
      return;
    }
    if (evento.ctrlKey || evento.metaKey || evento.shiftKey) return;
    var celula = evento.target.closest && evento.target.closest(".fis-tabela-marcavel tbody tr > td:first-child");
    if (!celula) {
      if (evento.target.closest && evento.target.closest(".fis-tabela-marcavel tbody td")) evento.stopPropagation();
      return;
    }
    evento.stopPropagation();
    evento.preventDefault();
    celula.dispatchEvent(new MouseEvent("mousedown", {
      bubbles: true, cancelable: true, button: 0, ctrlKey: !MAC, metaKey: MAC,
    }));
  }, true);

  document.addEventListener("click", function (evento) {
    var titulo = evento.target.closest && evento.target.closest(CABECALHO);
    if (!titulo) return;
    evento.stopPropagation();
    evento.preventDefault();
    var tabela = titulo.closest("shiny-data-frame");
    if (tabela && tabela.id && window.Shiny && Shiny.setInputValue) {
      Shiny.setInputValue(tabela.id + "_marcar_todas", Date.now(), { priority: "event" });
    }
  }, true);

  function registrar() {
    if (!(window.Shiny && Shiny.addCustomMessageHandler)) {
      setTimeout(registrar, 50);
      return;
    }
    Shiny.addCustomMessageHandler("fis_marcadas", function (mensagem) {
      var tabela = document.getElementById(mensagem.id);
      var caixa = tabela && (tabela.closest(".fis-tabela-marcavel") || tabela);
      if (!caixa) return;
      ["todas", "algumas", "vazia"].forEach(function (estado) {
        caixa.classList.toggle("fis-marcadas-" + estado, mensagem.estado === estado);
      });
    });
  }
  registrar();
})();
