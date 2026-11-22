(function () {
  var CLASSE_FAIXA = "comod-marcar-todos";
  var MARCA = "comodMarcarTodos";
  var CLASSES_RECONHECIDAS = [
    "comod-selectize-dropdown", "frota-selectize-dropdown", "tl-selectize-dropdown",
    "dev-selectize-dropdown", "rom-selectize-dropdown", "pde-selectize-dropdown",
  ];

  function ehFiltroDeComodato(instancia) {
    var classe = (instancia.settings && instancia.settings.dropdownClass) || "";
    var reconhecida = CLASSES_RECONHECIDAS.some(function (nome) { return classe.indexOf(nome) >= 0; });
    if (!reconhecida) return false;
    return instancia.settings.maxItems !== 1;
  }

  function valoresListados(instancia) {
    var valores = [];
    instancia.$dropdown_content.find("[data-value]").each(function () {
      var valor = this.getAttribute("data-value");
      if (valor) valores.push(valor);
    });
    return valores;
  }

  function marcarListados(instancia) {
    var listados = valoresListados(instancia);
    if (!listados.length) return;
    var juntos = instancia.items.slice();
    listados.forEach(function (valor) {
      if (juntos.indexOf(valor) < 0) juntos.push(valor);
    });

    instancia.setValue(juntos);
    instancia.setTextboxValue("");
    instancia.refreshOptions(false);
  }

  function desmarcarTudo(instancia) {
    instancia.setValue([]);
    instancia.setTextboxValue("");
    instancia.refreshOptions(false);
  }

  function atualizarFaixa(instancia) {
    var faixa = instancia.$dropdown.children("." + CLASSE_FAIXA);
    if (!faixa.length) return;
    var quantos = valoresListados(instancia).length;
    var temSelecao = instancia.items.length > 0;

    faixa.toggleClass("comod-marcar-todos-oculta", quantos === 0 && !temSelecao);
    faixa.find(".comod-marcar").text("Marcar os " + quantos).toggleClass("desligado", quantos === 0);
    faixa.find(".comod-desmarcar")
      .text(temSelecao ? "Desmarcar todos (" + instancia.items.length + ")" : "Desmarcar todos")
      .toggleClass("desligado", !temSelecao);
  }

  function montarFaixa(instancia) {
    var faixa = jQuery(
      '<div class="' + CLASSE_FAIXA + '">' +
      '<span class="comod-marcar" role="button" tabindex="0"></span>' +
      '<span class="comod-marcar-sep">&#183;</span>' +
      '<span class="comod-desmarcar" role="button" tabindex="0"></span>' +
      "</div>"
    );

    faixa.on("mousedown", ".comod-marcar", function (evento) {
      evento.preventDefault();
      if (!jQuery(this).hasClass("desligado")) marcarListados(instancia);
    });
    faixa.on("mousedown", ".comod-desmarcar", function (evento) {
      evento.preventDefault();
      if (!jQuery(this).hasClass("desligado")) desmarcarTudo(instancia);
    });
    instancia.$dropdown.prepend(faixa);
  }

  function ligar(instancia) {
    if (instancia[MARCA]) return;
    instancia[MARCA] = true;
    montarFaixa(instancia);
    instancia.on("dropdown_open", function () { atualizarFaixa(instancia); });

    instancia.on("type", function () { window.setTimeout(function () { atualizarFaixa(instancia); }, 0); });
    instancia.on("change", function () { atualizarFaixa(instancia); });
    atualizarFaixa(instancia);
  }

  function varrer() {
    document.querySelectorAll("select.selectized").forEach(function (campo) {
      var instancia = campo.selectize;
      if (instancia && ehFiltroDeComodato(instancia)) ligar(instancia);
    });
  }

  new MutationObserver(varrer).observe(document.documentElement, { childList: true, subtree: true });
  jQuery(document).on("shiny:value shiny:bound", function () { window.setTimeout(varrer, 0); });
  varrer();
})();
