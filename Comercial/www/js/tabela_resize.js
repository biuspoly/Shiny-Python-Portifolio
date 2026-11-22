(function () {
  var LARGURA_MINIMA = 40;

  var larguraCustom = {};

  function aplicarLargura(tabelas, indice, largura) {
    tabelas.forEach(function (tabela) {
      tabela.querySelectorAll("tr > :nth-child(" + (indice + 1) + ")").forEach(function (celula) {
        celula.style.setProperty("width", largura + "px", "important");
        celula.style.setProperty("min-width", largura + "px", "important");
        celula.style.setProperty("max-width", largura + "px", "important");
      });
    });
  }

  function prepararGrupo(grupo) {
    var tabelas = Array.prototype.slice.call(grupo.querySelectorAll("table"));
    if (!tabelas.length) return;

    var tabelaCabecalho = tabelas.find(function (t) {
      return t.querySelectorAll("thead th").length > 0;
    });
    if (!tabelaCabecalho) return;
    var cabecalhos = tabelaCabecalho.querySelectorAll("thead th");
    var chaveGrupo = grupo.id || grupo.className;

    cabecalhos.forEach(function (th, indice) {
      var texto = th.innerText.trim();
      var chaveCustom = chaveGrupo + "|" + texto;
      var largura = larguraCustom[chaveCustom];
      if (largura) aplicarLargura(tabelas, indice, largura);

      if (th.querySelector(".tabela-resize-handle")) return;

      var handle = document.createElement("span");
      handle.className = "tabela-resize-handle";
      handle.setAttribute("aria-hidden", "true");
      th.appendChild(handle);
      if (!th.style.position) th.style.position = "relative";

      handle.addEventListener("click", function (evento) {
        evento.stopPropagation();
      });

      handle.addEventListener("mousedown", function (evento) {
        evento.preventDefault();
        evento.stopPropagation();

        var inicioX = evento.clientX;
        var larguraInicial = th.getBoundingClientRect().width;
        document.body.classList.add("tabela-redimensionando-coluna");

        function mover(moveEvento) {
          var nova = Math.max(LARGURA_MINIMA, Math.round(larguraInicial + moveEvento.clientX - inicioX));
          larguraCustom[chaveCustom] = nova;
          aplicarLargura(tabelas, indice, nova);
        }
        function soltar() {
          document.body.classList.remove("tabela-redimensionando-coluna");
          document.removeEventListener("mousemove", mover);
          document.removeEventListener("mouseup", soltar);
        }
        document.addEventListener("mousemove", mover);
        document.addEventListener("mouseup", soltar);
      });
    });
  }

  function varrerTabelas() {
    document.querySelectorAll(".tabela-resize").forEach(prepararGrupo);
  }

  document.addEventListener("DOMContentLoaded", function () {
    varrerTabelas();
    var observador = new MutationObserver(function () {
      window.requestAnimationFrame(varrerTabelas);
    });
    observador.observe(document.body, { childList: true, subtree: true });
  });

  document.addEventListener("shiny:value", function () {
    window.setTimeout(varrerTabelas, 50);
  });
})();
