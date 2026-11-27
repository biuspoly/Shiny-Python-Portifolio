// O balao das notas da Apuracao (pag_apuracao.py::_livro): o DataGrid nao aceita um ui.popover dentro da linha, entao o
// balao nasce num ponto invisivel (.fis-nt-ancora) que este script poe ao lado da linha clicada, antes de o servidor
// abri-lo. O resto (abrir, fechar, o conteudo) e' do Shiny.
(function () {
  "use strict";

  document.addEventListener("click", function (evento) {
    var linha = evento.target.closest ? evento.target.closest(".fis-apu-livro shiny-data-frame tbody tr") : null;
    if (!linha) return;
    var caixa = linha.closest(".fis-apu-livro");
    var ancora = caixa ? caixa.querySelector(".fis-nt-ancora") : null;
    if (!ancora) return;
    var celula = linha.querySelector("td") || linha;
    var daCaixa = caixa.getBoundingClientRect();
    var daCelula = celula.getBoundingClientRect();
    ancora.style.top = (daCelula.top - daCaixa.top + daCelula.height / 2) + "px";
    ancora.style.left = (daCelula.right - daCaixa.left) + "px";
  }, true);
})();
